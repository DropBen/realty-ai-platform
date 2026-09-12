from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from realty.db import get_db, now
from realty.errors import DomainError
from realty.models import Activity, Commitment, Membership, Notification
from realty.repository import paginate, public, require
from realty.schemas import Date, Input
from realty.security import Principal, audit, principal

router = APIRouter(tags=["Commitments"])


class Review(Input):
    version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=250)
    status: Literal["confirmed", "done", "rejected"]
    due_at: Date | None = None
    responsible_user: str | None = None


@router.get("/commitments")
def list_commitments(
    status: str | None = None,
    page: int = Query(1, ge=1),
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    query = select(Commitment)
    if status:
        query = query.where(Commitment.status == status)
    return paginate(db, query.order_by(Commitment.created_at.desc(), Commitment.id), page, 25)


@router.post("/commitments/{commitment_id}/review")
def review(
    commitment_id: str,
    body: Review,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    actor.require("approve")
    item = db.scalar(select(Commitment).where(Commitment.id == commitment_id).with_for_update())
    if not item:
        raise DomainError("not_found", "This commitment is unavailable.", 404)
    if item.version != body.version:
        raise DomainError(
            "stale_commitment", "This commitment changed. Refresh before reviewing it.", 409
        )
    if body.status == "done" and item.status != "confirmed":
        raise DomainError("review_required", "Confirm the commitment before completing it.", 409)
    if body.status == "confirmed" and (not body.due_at or not body.responsible_user):
        raise DomainError("review_required", "Choose a due date and responsible team member.", 422)
    if body.responsible_user and not db.scalar(
        select(Membership).where(Membership.user_id == body.responsible_user)
    ):
        raise DomainError("invalid_assignee", "Choose a member of this organization.", 422)
    item.title, item.status, item.due_at, item.responsible_user = (
        body.title,
        body.status,
        body.due_at,
        body.responsible_user,
    )
    item.version += 1
    db.add(
        Activity(
            org_id=actor.org_id,
            contact_id=item.contact_id,
            kind="commitment",
            title=f"Commitment {item.status}: {item.title}"[:250],
            source_id=item.id,
        )
    )
    audit(db, actor, "commitment." + item.status, item.id)
    db.flush()
    return public(item)


def remind(db: Session, payload: dict[str, Any]) -> None:
    item = require(db, Commitment, payload["commitment_id"])
    if item.status != "confirmed" or item.version != payload["version"] or not item.due_at:
        return
    db.add(
        Notification(
            org_id=item.org_id,
            title="Commitment overdue" if item.due_at < now() else "Commitment due soon",
            body=item.title,
            link="/contacts/" + item.contact_id,
        )
    )
