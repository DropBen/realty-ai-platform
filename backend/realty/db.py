from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, create_engine, event
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    sessionmaker,
    with_loader_criteria,
)

from realty.config import settings


def now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def uid() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Record:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class TenantRecord(Record):
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False, "timeout": 30}
    if settings.database_url.startswith("sqlite")
    else {},
)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


@event.listens_for(engine, "connect")
def sqlite_constraints(connection: Any, _: Any) -> None:
    if engine.dialect.name == "sqlite":
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")


@event.listens_for(Session, "do_orm_execute")
def tenant_filter(state: Any) -> None:
    org_id = state.session.info.get("org_id")
    if org_id and (state.is_select or state.is_update or state.is_delete):
        state.statement = state.statement.options(
            with_loader_criteria(
                TenantRecord, lambda cls: cls.org_id == org_id, include_aliases=True
            )
        )


@event.listens_for(Session, "before_flush")
def tenant_write_guard(session: Session, _: Any, __: Any) -> None:
    org_id = session.info.get("org_id")
    if org_id:
        for obj in session.new | session.dirty | session.deleted:
            if isinstance(obj, TenantRecord) and obj.org_id != org_id:
                raise ValueError("Tenant boundary violation")


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
