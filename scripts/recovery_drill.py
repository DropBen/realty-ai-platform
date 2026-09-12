"""Execute a fictional two-tenant recovery drill, without changing application data."""

import argparse
import hashlib
import json
import os
import time
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from realty import backups
from realty.config import settings
from realty.db import Base, now
from realty.models import (
    AIAction,
    Contact,
    Document,
    Job,
    LoginSession,
    Membership,
    Organization,
    User,
)
from realty.operations import expected_revision
from realty.security import digest, hash_password
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--postgres", action="store_true")
    args = parser.parse_args()
    root = args.work_dir.resolve() / ("recovery-" + uuid4().hex)
    root.mkdir(parents=True)
    settings.storage_backend, settings.storage_path = "local", str(root / "source-documents")
    source_url = (
        os.environ.get("DRILL_DATABASE_URL", "")
        if args.postgres
        else "sqlite:///" + (root / "source.sqlite3").as_posix()
    )
    target_url = os.environ.get("RESTORE_DATABASE_URL") if args.postgres else None
    if args.postgres:
        from sqlalchemy.engine import make_url

        if (
            not source_url
            or not target_url
            or any(
                not (make_url(value).database or "").startswith("realty_drill_")
                for value in [source_url, target_url]
            )
        ):
            parser.error("Use dedicated realty_drill_* source and restore databases")
    engine = create_engine(source_url)
    if inspect(engine).get_table_names():
        raise ValueError("Drill source database must be empty")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)")
        )
        connection.execute(
            text("INSERT INTO alembic_version VALUES (:revision)"),
            {"revision": expected_revision()},
        )
    with Session(engine) as db:
        user = User(
            name="Fictional recovery operator",
            email="recovery-drill@example.com",
            password_hash=hash_password("fictional-recovery-password"),
        )
        orgs = [Organization(name=f"Fictional agency {index}", is_demo=True) for index in range(2)]
        db.add_all([user, *orgs])
        db.flush()
        for index, org in enumerate(orgs):
            contact = Contact(
                org_id=org.id, name=f"Fictional client {index}", email=f"client-{index}@example.com"
            )
            db.add_all([contact, Membership(org_id=org.id, user_id=user.id, role="owner")])
            db.flush()
            content = f"Fictional document for agency {index}".encode()
            key = org.id + "/drill.txt"
            backups.storage().put(key, content)
            db.add(
                Document(
                    org_id=org.id,
                    contact_id=contact.id,
                    name="drill.txt",
                    mime_type="text/plain",
                    storage_key=key,
                    sha256=hashlib.sha256(content).hexdigest(),
                    size=len(content),
                    text=content.decode(),
                    status="extracted",
                )
            )
            action = AIAction(
                org_id=org.id,
                contact_id=contact.id,
                kind="send_email",
                title="Review recovered email",
                reason="Fictional drill",
                payload={"to": contact.email, "subject": "Fictional", "body": "Fictional"},
                status="executing" if index else "approved",
                approved_by=user.id,
                approved_hash="fixture",
            )
            db.add(action)
            db.flush()
            db.add(
                Job(
                    org_id=org.id,
                    kind="execute_action",
                    payload={"action_id": action.id},
                    dedupe_key="drill-external",
                    status="running" if index else "queued",
                )
            )
        db.add(
            LoginSession(
                user_id=user.id,
                org_id=orgs[0].id,
                token_hash=digest("fictional-session"),
                csrf_hash=digest("fictional-csrf"),
                expires_at=now() + timedelta(hours=1),
            )
        )
        db.commit()
    started = time.monotonic()
    created = backups.backup(source_url, root / "snapshot", True)
    result = backups.restore(root / "snapshot", root / "restored", target_url)
    actual_url = target_url or "sqlite:///" + (root / "restored" / "database.sqlite3").as_posix()
    restored = create_engine(actual_url)
    with Session(restored) as db:
        assert db.scalar(select(LoginSession)) is None
        assert {action.status for action in db.scalars(select(AIAction))} == {
            "pending",
            "uncertain",
        }
        assert all(job.status == "dead" for job in db.scalars(select(Job)))
        for org in db.scalars(select(Organization)):
            db.info["org_id"] = org.id
            assert len(list(db.scalars(select(Contact)))) == 1
            assert len(list(db.scalars(select(Document)))) == 1
        db.info.clear()
    restored.dispose()
    overwrite_rejected = False
    try:
        backups.restore(root / "snapshot", root / "restored", target_url)
    except ValueError:
        overwrite_rejected = True
    # Corrupt only this drill's fictional snapshot after its successful restore.
    snapshot_file = root / "snapshot" / ("database.dump" if args.postgres else "database.sqlite3")
    with snapshot_file.open("ab") as stream:
        stream.write(b"corruption-test")
    corruption_rejected = False
    try:
        backups.verify_snapshot(root / "snapshot")
    except ValueError:
        corruption_rejected = True
    assert overwrite_rejected and corruption_rejected
    report = {
        "scope": "Executed isolated recovery using fictional data. No Azure recovery performed.",
        "database": created["database"],
        "duration_seconds": round(time.monotonic() - started, 3),
        "verified": result["verified"],
        "files_verified": result["files"],
        "rows_before_quarantine": result["inventory"]["rows"],
        "sessions_invalidated": result["sessions_invalidated"],
        "actions_quarantined": result["actions_quarantined"],
        "tenant_isolation_verified": True,
        "existing_target_rejected": overwrite_rejected,
        "checksum_corruption_rejected": corruption_rejected,
        "schema_revision": expected_revision(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    engine.dispose()
    print(
        json.dumps(
            {key: value for key, value in report.items() if key != "rows_before_quarantine"},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
