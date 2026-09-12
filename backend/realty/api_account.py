from typing import Any, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import EmailStr, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from realty.db import Base, TenantRecord, get_db
from realty.errors import DomainError
from realty.models import (
    Document,
    Integration,
    LoginSession,
    Membership,
    OAuthState,
    Organization,
    Subscription,
    User,
)
from realty.repository import public, require
from realty.schemas import Input
from realty.security import Principal, audit, principal, verify_password

router = APIRouter(prefix="/account", tags=["Account and lifecycle"])


class MemberInput(Input):
    email: EmailStr
    role: Literal["admin", "agent", "assistant", "viewer"]


class DeleteInput(Input):
    organization_name: str = Field(max_length=160)
    password: str = Field(max_length=128)


@router.get("/members")
def members(actor: Principal = Depends(principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.execute(select(Membership, User).join(User, User.id == Membership.user_id)).all()
    return {
        "items": [{"id": m.id, "name": u.name, "email": u.email, "role": m.role} for m, u in rows]
    }


@router.post("/members")
def add_member(
    body: MemberInput, actor: Principal = Depends(principal), db: Session = Depends(get_db)
) -> dict[str, Any]:
    actor.require("members")
    if body.role == "admin" and actor.role != "owner":
        raise DomainError("forbidden", "Only the owner can add an administrator.", 403)
    user = db.scalar(select(User).where(User.email == str(body.email).lower()))
    if not user:
        raise DomainError(
            "account_missing", "This person must create an account before being added.", 404
        )
    member = db.scalar(select(Membership).where(Membership.user_id == user.id))
    if member:
        raise DomainError("already_member", "This person already belongs to the organization.", 409)
    member = Membership(org_id=actor.org_id, user_id=user.id, role=body.role)
    db.add(member)
    db.flush()
    audit(db, actor, "membership.added", member.id, {"role": body.role})
    return public(member)


@router.put("/members/{member_id}")
def update_member(
    member_id: str,
    body: MemberInput,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    actor.require("members")
    member = require(db, Membership, member_id)
    if member.role == "owner" or (
        actor.role != "owner" and (member.role == "admin" or body.role == "admin")
    ):
        raise DomainError("forbidden", "This role change requires the organization owner.", 403)
    member.role = body.role
    audit(db, actor, "membership.role_changed", member.id, {"role": body.role})
    return public(member)


@router.get("/organizations")
def organizations(
    actor: Principal = Depends(principal), db: Session = Depends(get_db)
) -> dict[str, Any]:
    # Explicit cross-organization identity lookup, scoped by the authenticated user.
    with Session(db.get_bind()) as identity_db:
        rows = identity_db.execute(
            select(Organization, Membership)
            .join(Membership, Membership.org_id == Organization.id)
            .where(Membership.user_id == actor.user_id)
        ).all()
        return {"items": [{"id": org.id, "name": org.name, "role": m.role} for org, m in rows]}


@router.post("/organizations/{org_id}/switch")
def switch_organization(
    org_id: str, actor: Principal = Depends(principal), db: Session = Depends(get_db)
) -> dict[str, bool]:
    with Session(db.get_bind()) as identity_db:
        membership = identity_db.scalar(
            select(Membership).where(
                Membership.user_id == actor.user_id, Membership.org_id == org_id
            )
        )
        if not membership:
            raise DomainError("forbidden", "You do not belong to this organization.", 403)
    session = db.get(LoginSession, actor.session_id)
    assert session is not None
    session.org_id = org_id
    return {"ok": True}


@router.get("/export")
def export(actor: Principal = Depends(principal), db: Session = Depends(get_db)) -> dict[str, Any]:
    actor.require("members")
    result: dict[str, Any] = {}
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        if issubclass(cls, TenantRecord) and str(mapper.local_table) not in {
            "integrations",
            "sync_cursors",
            "jobs",
        }:
            count = db.scalar(select(func.count()).select_from(cls)) or 0
            if count > 20000:
                raise DomainError(
                    "export_size", "This workspace requires an operator-assisted bulk export.", 413
                )
            result[str(mapper.local_table)] = [public(r) for r in db.scalars(select(cls)).all()]
    audit(db, actor, "account.exported")
    return result


@router.post("/delete")
def delete_account(
    body: DeleteInput,
    response: Response,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    actor.require("delete_org")
    user, org = db.get(User, actor.user_id), db.get(Organization, actor.org_id)
    if (
        not user
        or not org
        or body.organization_name != org.name
        or not verify_password(body.password, user.password_hash)
    ):
        raise DomainError("confirmation_failed", "Organization name or password is incorrect.", 403)
    if db.scalar(select(Integration).where(Integration.status == "connected")):
        raise DomainError(
            "disconnect_required",
            "Disconnect all Google accounts before deleting this organization.",
            409,
        )
    subscription = db.scalar(select(Subscription))
    if (
        subscription
        and subscription.subscription_id
        and subscription.status not in {"canceled", "incomplete_expired"}
    ):
        raise DomainError(
            "cancel_required",
            "Cancel the subscription in the billing portal before deleting this organization.",
            409,
        )
    from realty.documents import storage

    for document in db.scalars(select(Document)).all():
        storage().delete(document.storage_key)
    session_ids = select(LoginSession.id).where(LoginSession.org_id == actor.org_id)
    db.execute(delete(OAuthState).where(OAuthState.session_id.in_(session_ids)))
    db.execute(delete(LoginSession).where(LoginSession.org_id == actor.org_id))
    for table in reversed(Base.metadata.sorted_tables):
        if "org_id" in table.c and table.name != "sessions":
            db.execute(delete(table).where(table.c.org_id == actor.org_id))
    db.delete(org)
    db.flush()
    with Session(db.get_bind()) as identity_db:
        other = identity_db.scalar(
            select(Membership.id).where(
                Membership.user_id == actor.user_id, Membership.org_id != actor.org_id
            )
        )
    if not other:
        db.delete(user)
    response.delete_cookie("realty_session", path="/")
    response.delete_cookie("realty_csrf", path="/")
    return {"ok": True}
