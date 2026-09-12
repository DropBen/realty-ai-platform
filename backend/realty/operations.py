"""Explicit operator and tenant-scoped operational views, without customer content."""

import hmac
import logging
import os
import socket
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from threading import Event, Thread
from typing import Any

from alembic.script import ScriptDirectory
from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from realty.config import settings
from realty.db import get_db, now
from realty.errors import DomainError
from realty.models import (
    AccountMail,
    AuthToken,
    Job,
    LoginSession,
    OAuthState,
    RateBucket,
    StorageDeletion,
    WorkerPulse,
)
from realty.repository import insert_for
from realty.security import Principal, principal

router = APIRouter(tags=["Operations"])
log = logging.getLogger("realty.operations")
PULSE_ID = socket.gethostname() + ":" + str(os.getpid())


@lru_cache
def expected_revision() -> str:
    return str(
        ScriptDirectory(str(Path(__file__).resolve().parents[1] / "migrations")).get_current_head()
    )


def assert_schema(db: Session) -> None:
    revisions = list(db.scalars(text("SELECT version_num FROM alembic_version")))
    if revisions != [expected_revision()]:
        raise DomainError(
            "migration_required",
            "Database migration is required before this version can serve requests.",
            503,
        )


def pulse(factory: sessionmaker[Session]) -> None:
    with factory() as db:
        db.execute(
            insert_for(db, WorkerPulse)
            .values(id=PULSE_ID, last_seen=now())
            .on_conflict_do_update(index_elements=[WorkerPulse.id], set_={"last_seen": now()})
        )
        db.commit()


class WorkerHeartbeat:
    def __init__(self, factory: sessionmaker[Session]):
        self.factory = factory
        self.stop = Event()
        self.thread: Thread | None = None

    def run(self) -> None:
        while not self.stop.wait(15):
            try:
                pulse(self.factory)
            except Exception:
                log.error("worker.heartbeat_failed")

    def start(self) -> None:
        pulse(self.factory)
        if self.factory.kw["bind"].dialect.name == "postgresql":
            self.thread = Thread(target=self.run, name="realty-worker-health", daemon=True)
            self.thread.start()

    def close(self) -> None:
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=2)


def maintenance(factory: sessionmaker[Session]) -> None:
    from realty.documents import purge_storage

    with factory() as db:
        expired_sessions = select(LoginSession.id).where(LoginSession.expires_at < now())
        db.execute(
            delete(OAuthState).where(
                (OAuthState.expires_at < now()) | OAuthState.session_id.in_(expired_sessions)
            )
        )
        db.execute(delete(LoginSession).where(LoginSession.expires_at < now()))
        db.execute(delete(AuthToken).where(AuthToken.expires_at < now() - timedelta(days=1)))
        db.execute(delete(AccountMail).where(AccountMail.created_at < now() - timedelta(days=7)))
        db.execute(delete(RateBucket).where(RateBucket.expires_at < now()))
        db.execute(delete(WorkerPulse).where(WorkerPulse.last_seen < now() - timedelta(days=1)))
        purge_storage(db)
        db.commit()


def queue_state(db: Session) -> dict[str, Any]:
    counts = {
        status: count
        for status, count in db.execute(select(Job.status, func.count(Job.id)).group_by(Job.status))
    }
    oldest = db.scalar(
        select(func.min(Job.available_at)).where(Job.status == "queued", Job.available_at <= now())
    )
    pulse_at = db.scalar(select(func.max(WorkerPulse.last_seen)))
    return {
        "jobs": counts,
        "oldest_due_seconds": max(0, int((now() - oldest).total_seconds())) if oldest else 0,
        "worker_available": bool(pulse_at and pulse_at > now() - timedelta(seconds=90)),
        "worker_last_seen": pulse_at,
    }


@router.get("/operations")
def operational_status(
    actor: Principal = Depends(principal), db: Session = Depends(get_db, scope="function")
) -> dict[str, Any]:
    actor.require("members")
    assert_schema(db)
    return {
        **queue_state(db),
        "schema_revision": expected_revision(),
        "storage_cleanup_failures": db.scalar(
            select(func.count())
            .select_from(StorageDeletion)
            .where(StorageDeletion.org_id == actor.org_id, StorageDeletion.attempts >= 5)
        )
        or 0,
    }


def metrics(request: Request, db: Session) -> PlainTextResponse:
    from realty.observability import render_metrics

    if not settings.metrics_token:
        raise DomainError("metrics_unconfigured", "Operator metrics are not configured.", 503)
    token = request.headers.get("authorization", "")
    if not hmac.compare_digest(token, "Bearer " + settings.metrics_token):
        raise DomainError("forbidden", "Operator authentication is required.", 403)
    state = queue_state(db)
    rows = [
        render_metrics(),
        "# TYPE realty_worker_available gauge",
        f"realty_worker_available {int(state['worker_available'])}",
        "# TYPE realty_queue_oldest_due_seconds gauge",
        f"realty_queue_oldest_due_seconds {state['oldest_due_seconds']}",
    ]
    for status in ["queued", "running", "done", "dead"]:
        rows.append(f'realty_jobs{{status="{status}"}} {state["jobs"].get(status, 0)}')
    return PlainTextResponse("\n".join(rows) + "\n", media_type="text/plain; version=0.0.4")
