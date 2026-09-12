from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from realty.config import settings
from realty.db import now
from sqlalchemy import MetaData, create_engine, select, text


def test_upgrade_invalidates_unbound_authority_and_preserves_history(monkeypatch):
    path = Path("data") / f"migration-{uuid4()}.db"
    monkeypatch.setattr(settings, "database_url", "sqlite:///" + path.as_posix())
    config = Config("alembic.ini")
    engine = create_engine(settings.database_url)
    try:
        command.upgrade(config, "2375a43c78e9")
        metadata = MetaData()
        metadata.reflect(engine)
        tables = metadata.tables
        timestamps = {"created_at": now(), "updated_at": now()}
        with engine.begin() as db:
            db.execute(
                tables["organizations"]
                .insert()
                .values(
                    id="org", name="Migration fixture", is_demo=True, timezone="UTC", **timestamps
                )
            )
            db.execute(
                tables["users"]
                .insert()
                .values(
                    id="user",
                    name="Test",
                    email="migration@example.com",
                    password_hash="unused",
                    **timestamps,
                )
            )
            db.execute(
                tables["sessions"]
                .insert()
                .values(
                    id="session",
                    user_id="user",
                    org_id="org",
                    token_hash="token",
                    csrf_hash="csrf",
                    expires_at=now() + timedelta(minutes=10),
                    **timestamps,
                )
            )
            db.execute(
                tables["oauth_states"]
                .insert()
                .values(
                    id="oauth",
                    state_hash="state",
                    session_id="session",
                    verifier="verifier",
                    expires_at=now() + timedelta(minutes=10),
                    **timestamps,
                )
            )
            for status in ["approved", "succeeded"]:
                db.execute(
                    tables["ai_actions"]
                    .insert()
                    .values(
                        id=status,
                        org_id="org",
                        kind="crm_update",
                        title="Budget",
                        reason="Evidence",
                        priority="normal",
                        confidence=1,
                        permission="suggested",
                        payload={},
                        status=status,
                        approved_by="user",
                        approved_hash="old-hash",
                        version=2,
                        **timestamps,
                    )
                )
        command.upgrade(config, "head")
        command.check(config)
        with engine.connect() as db:
            assert db.scalar(select(tables["oauth_states"].c.id)) is None
            rows = {
                row.id: row
                for row in db.execute(
                    text("SELECT id, status, version, approved_hash FROM ai_actions")
                )
            }
            assert (
                rows["approved"].status,
                rows["approved"].version,
                rows["approved"].approved_hash,
            ) == ("pending", 3, None)
            assert (rows["succeeded"].status, rows["succeeded"].version) == ("succeeded", 2)
        command.downgrade(config, "2375a43c78e9")
        command.upgrade(config, "head")
        command.check(config)
    finally:
        engine.dispose()
        path.unlink(missing_ok=True)
