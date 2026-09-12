"""Renewable PostgreSQL job leases and transaction fencing.

SQLite remains a single-worker development backend. It uses the same transaction
fence, without a second connection writing concurrently to an in-memory database.
"""

import logging
from datetime import timedelta
from threading import Event, Thread
from types import TracebackType
from typing import Any

from sqlalchemy import event, select, update
from sqlalchemy.orm import Session, sessionmaker

from realty.db import now
from realty.errors import DomainError
from realty.models import Job

LEASE_SECONDS = 600
RENEW_SECONDS = 30
log = logging.getLogger("realty.worker")


def check_fence(db: Session, job_id: str, org_id: str, attempt: int) -> None:
    table = Job.__table__
    owned = db.connection().scalar(
        select(table.c.id)
        .where(
            table.c.id == job_id,
            table.c.org_id == org_id,
            table.c.attempts == attempt,
            table.c.status == "running",
            table.c.lease_until > now(),
        )
        .with_for_update()
    )
    if not owned:
        raise DomainError("lease_lost", "This worker no longer owns the job.", 409)


def renew_lease(factory: sessionmaker[Session], job_id: str, org_id: str, attempt: int) -> bool:
    with factory() as db:
        renewed = db.scalar(
            update(Job)
            .where(
                Job.id == job_id,
                Job.org_id == org_id,
                Job.attempts == attempt,
                Job.status == "running",
                Job.lease_until > now(),
            )
            .values(lease_until=now() + timedelta(seconds=LEASE_SECONDS))
            .returning(Job.id)
        )
        db.commit()
        return renewed is not None


class Lease:
    def __init__(self, db: Session, factory: sessionmaker[Session], job: Job):
        self.db, self.factory = db, factory
        self.job_id, self.org_id, self.attempt = job.id, job.org_id, job.attempts
        self.stop, self.lost = Event(), Event()
        self.thread: Thread | None = None

    def guard(self, session: Session, *args: Any) -> None:
        if self.lost.is_set():
            raise DomainError("lease_lost", "Worker lease renewal failed.", 409)
        check_fence(session, self.job_id, self.org_id, self.attempt)

    def heartbeat(self) -> None:
        while not self.stop.wait(RENEW_SECONDS):
            try:
                if renew_lease(self.factory, self.job_id, self.org_id, self.attempt):
                    continue
            except Exception:
                log.warning("worker.renewal_failed", extra={"job_id": self.job_id})
            self.lost.set()
            return

    def __enter__(self) -> "Lease":
        self.guard(self.db)
        self.db.commit()
        self.db.info["job_fence"] = (self.job_id, self.org_id, self.attempt)
        event.listen(self.db, "before_flush", self.guard)
        event.listen(self.db, "before_commit", self.guard)
        if self.db.get_bind().dialect.name == "postgresql":
            self.thread = Thread(target=self.heartbeat, daemon=True, name="realty-job-lease")
            self.thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.stop.set()
        event.remove(self.db, "before_flush", self.guard)
        event.remove(self.db, "before_commit", self.guard)
        self.db.info.pop("job_fence", None)
        if self.thread:
            self.thread.join(timeout=2)


def checkpoint(db: Session) -> None:
    """Bound import transactions without advancing a sync cursor prematurely."""
    if db.info.get("job_fence"):
        db.commit()
