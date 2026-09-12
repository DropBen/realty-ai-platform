from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from realty.config import settings
from realty.db import now
from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.exc import IntegrityError


def test_calendar_migration_preserves_constraints_and_requires_new_review(monkeypatch):
    path = Path("data") / f"calendar-migration-{uuid4()}.db"
    monkeypatch.setattr(settings, "database_url", "sqlite:///" + path.as_posix())
    config = Config("alembic.ini")
    engine = create_engine(settings.database_url)
    try:
        command.upgrade(config, "6bda8c204a71")
        metadata = MetaData()
        metadata.reflect(engine)
        with engine.begin() as db:
            timestamps = {"created_at": now(), "updated_at": now()}
            db.execute(
                metadata.tables["organizations"]
                .insert()
                .values(id="org", name="Migration", is_demo=True, timezone="UTC", **timestamps)
            )
            db.execute(
                text(
                    "INSERT INTO appointments "
                    "(id,org_id,title,start_at,end_at,location,status,created_at,updated_at,external_id) VALUES "
                    "('event','org','Preserved event','2027-01-01 12:00:00','2027-01-01 13:00:00','','confirmed',"
                    "'2026-09-12','2026-09-12','user:primary:event')"
                )
            )
            db.execute(
                metadata.tables["ai_actions"]
                .insert()
                .values(
                    id="action",
                    org_id="org",
                    kind="calendar_delete",
                    title="Delete",
                    reason="Review",
                    priority="normal",
                    confidence=1,
                    permission="approval_required",
                    payload={"appointment_id": "event"},
                    status="approved",
                    approved_hash="old",
                    version=2,
                    **timestamps,
                )
            )
            for index in range(2):
                db.execute(
                    metadata.tables["jobs"]
                    .insert()
                    .values(
                        id=f"sync-{index}",
                        org_id="org",
                        kind="gmail_sync",
                        payload={"user_id": "user"},
                        dedupe_key=f"old-request-{index}",
                        status="queued",
                        attempts=0,
                        available_at=now(),
                        **timestamps,
                    )
                )
        command.upgrade(config, "head")
        command.check(config)
        with engine.connect() as db:
            assert db.execute(
                text("SELECT status,version,approved_hash FROM ai_actions")
            ).one() == ("pending", 3, None)
            from realty.jobs import sync_resource

            jobs = db.execute(text("SELECT status,resource_key FROM jobs ORDER BY id")).all()
            assert [row.status for row in jobs] == ["queued", "done"]
            assert {row.resource_key for row in jobs} == {
                sync_resource("gmail_sync", {"user_id": "user"})
            }
        for revision in ["6bda8c204a71", "head"]:
            with pytest.raises(IntegrityError), engine.begin() as db:
                db.execute(text("UPDATE appointments SET end_at=start_at"))
            if revision == "head":
                command.upgrade(config, revision)
            else:
                command.downgrade(config, revision)
        command.check(config)
    finally:
        engine.dispose()
        path.unlink(missing_ok=True)
