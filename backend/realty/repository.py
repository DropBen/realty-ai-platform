from typing import Any, TypeVar

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from realty.db import Base, TenantRecord
from realty.errors import DomainError
from realty.models import Contact, Membership, Property, User

T = TypeVar("T", bound=Base)
PRIVATE_FIELDS = {"password_hash", "token_ciphertext", "token_hash", "csrf_hash", "storage_key"}


def public(row: Any) -> dict[str, Any]:
    if isinstance(row, User):
        return {
            "id": row.id,
            "name": row.name,
            "email": row.email,
            "email_verified_at": row.email_verified_at,
            "mfa_enabled": bool(row.mfa_ciphertext),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    return {
        c.key: getattr(row, c.key)
        for c in inspect(row).mapper.column_attrs
        if c.key not in PRIVATE_FIELDS and c.key != "org_id"
    }


def require[T: Base](db: Session, model: type[T], record_id: str) -> T:
    row = db.scalar(select(model).where(model.id == record_id))  # type: ignore[attr-defined]
    if row is None:
        raise DomainError("not_found", "This record is unavailable.", 404)
    if isinstance(row, TenantRecord) and row.org_id != db.info.get("org_id"):
        raise DomainError("not_found", "This record is unavailable.", 404)
    return row


def validate_refs(db: Session, values: dict[str, Any]) -> None:
    if values.get("contact_id"):
        require(db, Contact, values["contact_id"])
    if values.get("property_id"):
        require(db, Property, values["property_id"])
    if values.get("assigned_to"):
        member = db.scalar(select(Membership).where(Membership.user_id == values["assigned_to"]))
        if not member:
            raise DomainError("invalid_assignee", "Choose a member of this organization.")


def paginate(db: Session, statement: Any, page: int, size: int) -> dict[str, Any]:
    total = db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0
    rows = db.scalars(statement.offset((page - 1) * size).limit(size)).all()
    return {"items": [public(row) for row in rows], "total": total, "page": page, "page_size": size}
