from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from realty.db import get_db, now
from realty.errors import DomainError
from realty.intelligence import profile_context
from realty.jobs import emit, followup
from realty.models import (
    Activity,
    Appointment,
    Contact,
    Deal,
    Fact,
    Organization,
    Preference,
    Property,
    Task,
    Transaction,
)
from realty.repository import locked_preference, paginate, public, require, validate_refs
from realty.schemas import (
    AppointmentInput,
    ContactInput,
    DealInput,
    NoteInput,
    PreferenceInput,
    PropertyInput,
    TaskInput,
    TransactionInput,
)
from realty.security import Principal, audit, principal

router = APIRouter(tags=["CRM"])
RESOURCES: dict[str, tuple[Any, Any, str]] = {
    "contacts": (Contact, ContactInput, "name"),
    "properties": (Property, PropertyInput, "address"),
    "deals": (Deal, DealInput, "title"),
    "tasks": (Task, TaskInput, "title"),
    "appointments": (Appointment, AppointmentInput, "title"),
    "transactions": (Transaction, TransactionInput, "title"),
}


def resource(name: str) -> tuple[Any, Any, str]:
    if name not in RESOURCES:
        raise DomainError("not_found", "Unknown CRM resource.", 404)
    return RESOURCES[name]


def values_for(db: Session, name: str, body: dict[str, Any]) -> dict[str, Any]:
    _, schema, _ = resource(name)
    try:
        values = schema.model_validate(body).model_dump()
    except ValidationError as exc:
        messages = "; ".join(
            f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors(include_input=False)
        )
        raise DomainError("validation_error", messages, 422) from exc
    validate_refs(db, values)
    if values.get("deal_id"):
        require(db, Deal, values["deal_id"])
    return values  # type: ignore[no-any-return]


@router.get("/crm/{name}")
def list_records(
    name: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    q: str = Query("", max_length=200),
    kind: str | None = None,
    status: str | None = None,
    sort: str = "created_at",
    direction: str = "desc",
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    model, _, label = resource(name)
    statement = select(model)
    if q:
        statement = statement.where(
            getattr(model, label).ilike(
                "%" + q.replace("%", "\\%").replace("_", "\\_") + "%", escape="\\"
            )
        )
    if name == "contacts":
        statement = statement.where(Contact.archived.is_(False))
        if kind:
            statement = statement.where(Contact.kind == kind)
    if status and hasattr(model, "status"):
        statement = statement.where(model.status == status)
    allowed_sorts = {"created_at", label, "updated_at"} | (
        {"price"} if name == "properties" else set()
    )
    if sort not in allowed_sorts or direction not in {"asc", "desc"}:
        raise DomainError("invalid_sort", "Unsupported sort order.", 422)
    column = getattr(model, sort)
    return paginate(
        db,
        statement.order_by(column.desc() if direction == "desc" else column.asc(), model.id),
        page,
        page_size,
    )


@router.post("/crm/{name}", status_code=201)
def create_record(
    name: str,
    body: dict[str, Any],
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    actor.require("write")
    model, _, label = resource(name)
    values = values_for(db, name, body)
    if name == "appointments":
        check_conflicts(db, values)
    row = model(org_id=actor.org_id, **values)
    db.add(row)
    db.flush()
    audit(db, actor, name + ".created", row.id)
    contact_id = row.id if name == "contacts" else values.get("contact_id")
    db.add(
        Activity(
            org_id=actor.org_id,
            contact_id=contact_id,
            kind="crm_change",
            title="Created " + str(getattr(row, label)),
            source_id=row.id,
        )
    )
    if name == "contacts" and row.kind == "lead":
        emit(db, actor, "LEAD_CREATED", row.id)
    elif name == "properties":
        emit(db, actor, "PROPERTY_CREATED", row.id)
    return public(row)


@router.get("/crm/{name}/{record_id}")
def get_record(
    name: str,
    record_id: str,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    model, _, _ = resource(name)
    return public(require(db, model, record_id))


@router.put("/crm/{name}/{record_id}")
def edit_record(
    name: str,
    record_id: str,
    body: dict[str, Any],
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    actor.require("write")
    model, _, label = resource(name)
    row = require(db, model, record_id)
    if name == "appointments" and row.external_id:
        raise DomainError(
            "approval_required",
            "Changes to Google events require an approved calendar action.",
            409,
        )
    values = values_for(db, name, body)
    if name == "appointments":
        check_conflicts(db, values, record_id)
    for key, value in values.items():
        setattr(row, key, value)
    if name == "contacts":
        row.version += 1
    audit(db, actor, name + ".updated", row.id, {"fields": sorted(values)})
    db.add(
        Activity(
            org_id=actor.org_id,
            contact_id=row.id if name == "contacts" else values.get("contact_id"),
            kind="crm_change",
            title="Updated " + str(getattr(row, label)),
            source_id=row.id,
        )
    )
    db.flush()
    return public(row)


def check_conflicts(db: Session, values: dict[str, Any], exclude: str = "") -> None:
    # Serialize appointment checks and writes within the workspace transaction.
    org_id = db.info["org_id"]
    if db.bind is not None and db.bind.dialect.name == "sqlite":
        db.execute(
            update(Organization).where(Organization.id == org_id).values(name=Organization.name)
        )
    else:
        db.scalar(select(Organization).where(Organization.id == org_id).with_for_update())
    conflict = db.scalar(
        select(Appointment).where(
            Appointment.id != exclude,
            Appointment.status != "cancelled",
            Appointment.start_at < values["end_at"],
            Appointment.end_at > values["start_at"],
        )
    )
    if conflict:
        raise DomainError("calendar_conflict", "This time overlaps an existing appointment.", 409)


@router.get("/contacts/{contact_id}/profile")
def profile(
    contact_id: str,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    return profile_context(db, contact_id)


@router.put("/contacts/{contact_id}/preferences")
def preferences(
    contact_id: str,
    body: PreferenceInput,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    actor.require("write")
    row = locked_preference(db, contact_id)
    if not row:
        row = Preference(org_id=actor.org_id, contact_id=contact_id)
        db.add(row)
        db.flush()
    values = body.model_dump()
    for key, value in values.items():
        if getattr(row, key) != value:
            setattr(row, key, value)
            db.add(
                Fact(
                    org_id=actor.org_id,
                    contact_id=contact_id,
                    field=key,
                    value=value,
                    source_type="manual",
                    source_id=actor.user_id,
                    confidence=1,
                    method="manual_entry",
                    state="confirmed",
                    verified_by=actor.user_id,
                )
            )
    audit(db, actor, "preferences.updated", contact_id, {"fields": sorted(values)})
    db.add(
        Activity(
            org_id=actor.org_id,
            contact_id=contact_id,
            kind="crm_change",
            title="Updated buying preferences",
        )
    )
    db.flush()
    return public(row)


@router.post("/contacts/{contact_id}/notes", status_code=201)
def note(
    contact_id: str,
    body: NoteInput,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    actor.require("write")
    contact = require(db, Contact, contact_id)
    row = Activity(org_id=actor.org_id, contact_id=contact_id, **body.model_dump())
    if body.kind == "call":
        contact.last_contact_at = now()
    db.add(row)
    db.flush()
    audit(db, actor, "activity.created", row.id)
    return public(row)


@router.post("/contacts/{contact_id}/followup")
def draft_followup(
    contact_id: str,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    actor.require("write")
    return public(followup(db, actor, require(db, Contact, contact_id)))


@router.get("/availability")
def availability(
    days: int = Query(7, ge=1, le=30),
    duration: int = Query(60, ge=15, le=240),
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    from zoneinfo import ZoneInfo

    from realty.models import Organization

    org = db.get(Organization, actor.org_id)
    zone = ZoneInfo(org.timezone if org else "America/New_York")
    from datetime import UTC

    start = (
        now()
        .replace(tzinfo=UTC)
        .astimezone(zone)
        .replace(hour=9, minute=0, second=0, microsecond=0)
    )
    appointments = db.scalars(
        select(Appointment).where(
            Appointment.status != "cancelled",
            Appointment.end_at > now(),
            Appointment.start_at < now() + timedelta(days=days + 1),
        )
    ).all()
    slots = []
    for day in range(days):
        date = start + timedelta(days=day)
        if date.weekday() >= 5:
            continue
        for hour in range(9, 17):
            local_start = date.replace(hour=hour)
            local_end = local_start + timedelta(minutes=duration)
            if (
                local_end > date.replace(hour=17, minute=0)
                or local_end.date() != local_start.date()
            ):
                continue
            candidate = local_start.astimezone(UTC).replace(tzinfo=None)
            end = local_end.astimezone(UTC).replace(tzinfo=None)
            if candidate > now() and not any(
                a.start_at < end and a.end_at > candidate for a in appointments
            ):
                slots.append(
                    {
                        "start_at": candidate,
                        "end_at": end,
                        "reason": "Within office hours with no recorded calendar conflict",
                    }
                )
    return {
        "slots": slots[:20],
        "timezone": str(zone),
        "limitations": "Travel time and unsynced calendars are not considered.",
    }
