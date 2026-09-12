"""Quiesced database + document snapshots and restore into an empty target.

Credentials stay in environment variables. Snapshot files contain private data;
operators must use an encrypted, access-controlled backup location.
"""

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, delete, func, inspect, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from realty.db import Base
from realty.documents import storage
from realty.models import AccountMail, AIAction, AuthToken, Document, Job, LoginSession, OAuthState


def checked_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or Path(relative).is_absolute():
        raise ValueError("Invalid backup path")
    return path


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pg_command(command: str, database_url: str, arguments: list[str]) -> None:
    executable = shutil.which(
        command, path=os.environ.get("PG_BIN_DIR", os.environ.get("PATH", ""))
    )
    if not executable:
        raise ValueError(f"Install PostgreSQL client tools before running {command}")
    url = make_url(database_url)
    environment = os.environ.copy()
    environment.update(
        {
            "PGHOST": url.host or "localhost",
            "PGPORT": str(url.port or 5432),
            "PGDATABASE": url.database or "",
            "PGUSER": url.username or "",
            "PGPASSWORD": url.password or "",
            "PGSSLMODE": str(url.query.get("sslmode", "prefer")),
        }
    )
    if url.query.get("sslrootcert"):
        environment["PGSSLROOTCERT"] = str(url.query["sslrootcert"])
    result = subprocess.run(
        [executable, *arguments], env=environment, capture_output=True, timeout=300, check=False
    )
    if result.returncode:
        raise RuntimeError(
            f"{command} failed. Check protected database logs and client compatibility."
        )


def inventory(database_url: str) -> dict[str, Any]:
    engine = create_engine(database_url)
    try:
        with Session(engine) as db:
            return {
                "revision": db.scalar(text("SELECT version_num FROM alembic_version")),
                "rows": {
                    table.name: db.scalar(select(func.count()).select_from(table)) or 0
                    for table in Base.metadata.sorted_tables
                },
            }
    finally:
        engine.dispose()


def backup(database_url: str, destination: Path, quiesced: bool) -> dict[str, Any]:
    if not quiesced:
        raise ValueError("Pause API writes and workers, then explicitly confirm quiescence")
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    url = make_url(database_url)
    engine = create_engine(database_url)
    manifest: dict[str, Any] = {
        "format": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "database": url.get_backend_name(),
        "inventory": inventory(database_url),
        "files": {},
    }
    try:
        if url.get_backend_name() == "sqlite":
            if not url.database or not Path(url.database).is_file():
                raise ValueError("Backup requires an existing file-backed SQLite database")
            snapshot = destination / "database.sqlite3"
            with sqlite3.connect(url.database) as source, sqlite3.connect(snapshot) as target:
                source.backup(target)
        elif url.get_backend_name() == "postgresql":
            snapshot = destination / "database.dump"
            pg_command(
                "pg_dump",
                database_url,
                ["--format=custom", "--no-owner", "--no-acl", "--file", str(snapshot)],
            )
        else:
            raise ValueError("Unsupported database backend")
        manifest["files"][snapshot.name] = checksum(snapshot)
        with Session(engine) as db:
            for document in db.scalars(select(Document)):
                path = checked_path(destination, "documents/" + document.storage_key)
                content = storage().get(document.storage_key)
                if hashlib.sha256(content).hexdigest() != document.sha256:
                    raise ValueError("A source document failed its stored checksum")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                manifest["files"][path.relative_to(destination).as_posix()] = checksum(path)
        if inventory(database_url) != manifest["inventory"]:
            raise ValueError("Database changed during backup; repeat with writes paused")
        (destination / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        return {
            "database": manifest["database"],
            "files": len(manifest["files"]),
            "inventory": manifest["inventory"],
        }
    finally:
        engine.dispose()


def verify_snapshot(source: Path) -> dict[str, Any]:
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != 1 or manifest.get("database") not in {"sqlite", "postgresql"}:
        raise ValueError("Unsupported snapshot format")
    for relative, digest in manifest["files"].items():
        if checksum(checked_path(source, relative)) != digest:
            raise ValueError("Snapshot checksum mismatch")
    return manifest  # type: ignore[no-any-return]


def quarantine(db: Session) -> dict[str, int]:
    sessions = db.scalar(select(func.count()).select_from(LoginSession)) or 0
    db.execute(delete(OAuthState))
    db.execute(delete(LoginSession))
    db.execute(delete(AuthToken))
    db.execute(update(AccountMail).values(body_ciphertext=None))
    db.execute(
        update(Job)
        .where(Job.kind == "account_mail", Job.status.in_(["queued", "running"]))
        .values(status="dead", error_code="restored_token_invalidated")
    )
    actions = list(
        db.scalars(
            select(AIAction).where(
                AIAction.status.in_(["approved", "executing"]),
            )
        )
    )
    for action in actions:
        action.status = (
            "uncertain"
            if action.status == "executing"
            and action.kind
            in {"send_email", "calendar_create", "calendar_update", "calendar_delete"}
            else "pending"
        )
        action.approved_by, action.approved_hash = None, None
        action.error_code = "restore_review_required"
        action.version += 1
    # All action jobs need explicit review after recovery; never auto-send recovered work.
    db.execute(
        update(Job)
        .where(Job.kind == "execute_action", Job.status.in_(["queued", "running"]))
        .values(status="dead", error_code="restore_review_required")
    )
    db.commit()
    return {"sessions_invalidated": sessions, "actions_quarantined": len(actions)}


def restore(
    source: Path, destination: Path, target_database_url: str | None = None
) -> dict[str, Any]:
    source, destination = source.resolve(), destination.resolve()
    manifest = verify_snapshot(source)
    if destination.exists():
        raise ValueError("Restore destination must be new; existing data is never overwritten")
    if manifest["database"] == "postgresql":
        if (
            not target_database_url
            or make_url(target_database_url).get_backend_name() != "postgresql"
        ):
            raise ValueError(
                "Set RESTORE_DATABASE_URL to a separately created, empty PostgreSQL database"
            )
        target = create_engine(target_database_url)
        try:
            if inspect(target).get_table_names():
                raise ValueError("PostgreSQL restore target must be empty")
        finally:
            target.dispose()
    destination.mkdir(parents=True, exist_ok=False)
    if manifest["database"] == "sqlite":
        shutil.copyfile(source / "database.sqlite3", destination / "database.sqlite3")
        target_database_url = "sqlite:///" + (destination / "database.sqlite3").as_posix()
    else:
        assert target_database_url is not None
        pg_command(
            "pg_restore",
            target_database_url,
            [
                "--no-owner",
                "--no-acl",
                "--single-transaction",
                "--exit-on-error",
                "--dbname",
                make_url(target_database_url).database or "",
                str(source / "database.dump"),
            ],
        )
    for relative in manifest["files"]:
        if relative.startswith("documents/"):
            path = checked_path(destination, relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(checked_path(source, relative), path)
    if inventory(target_database_url) != manifest["inventory"]:
        raise ValueError("Restored row counts or schema revision differ from the snapshot")
    engine = create_engine(target_database_url)
    try:
        with Session(engine) as db:
            if (
                engine.dialect.name == "sqlite"
                and db.execute(text("PRAGMA foreign_key_check")).first()
            ):
                raise ValueError("Restored foreign keys are inconsistent")
            for document in db.scalars(select(Document)):
                if (
                    checksum(checked_path(destination, "documents/" + document.storage_key))
                    != document.sha256
                ):
                    raise ValueError("Restored document differs from its database checksum")
            safety = quarantine(db)
    finally:
        engine.dispose()
    return {
        "verified": True,
        "database": manifest["database"],
        "files": len(manifest["files"]),
        "inventory": manifest["inventory"],
        **safety,
    }
