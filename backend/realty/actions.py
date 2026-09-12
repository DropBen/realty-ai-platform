import json
from datetime import timedelta
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from realty.db import now
from realty.errors import DomainError
from realty.models import (
    Activity,
    AIAction,
    Appointment,
    Contact,
    Fact,
    Job,
    Membership,
    Preference,
    Task,
    Usage,
)
from realty.repository import locked_preference, require, validate_refs
from realty.schemas import (
    ActionInput,
    AppointmentInput,
    CalendarChange,
    CRMUpdate,
    Decision,
    EmailPayload,
    PreferenceInput,
    TaskInput,
)
from realty.security import Principal, audit, digest

EXTERNAL_KINDS = {"send_email", "calendar_create", "calendar_update", "calendar_delete"}
PAYLOAD_SCHEMAS: dict[str, type[BaseModel]] = {
    "crm_update": CRMUpdate,
    "create_task": TaskInput,
    "send_email": EmailPayload,
    "calendar_create": AppointmentInput,
    "calendar_update": CalendarChange,
    "calendar_delete": CalendarChange,
}


def checked_payload(
    db: Session, kind: str, payload: dict[str, Any], contact_id: str | None
) -> dict[str, Any]:
    if kind not in PAYLOAD_SCHEMAS:
        raise DomainError("invalid_action", "Unsupported action type.", 422)
    try:
        checked = (
            PAYLOAD_SCHEMAS[kind]
            .model_validate(payload)
            .model_dump(mode="json", exclude_unset=True)
        )
    except ValidationError as exc:
        raise DomainError(
            "invalid_action", "The proposed action contains invalid fields.", 422
        ) from exc
    validate_refs(db, checked)
    if kind == "crm_update":
        preference = db.scalar(
            select(Preference).where(Preference.contact_id == checked["contact_id"])
        )
        current = (
            {key: getattr(preference, key) for key in PreferenceInput.model_fields}
            if preference
            else {}
        )
        try:
            PreferenceInput.model_validate({**current, **checked["changes"]})
        except ValidationError as exc:
            raise DomainError(
                "invalid_action",
                "The change conflicts with the client's existing preferences.",
                422,
            ) from exc
    if contact_id:
        contact = require(db, Contact, contact_id)
        if checked.get("contact_id", contact_id) != contact_id:
            raise DomainError(
                "contact_mismatch", "The action and its payload refer to different contacts."
            )
        if kind == "send_email" and contact.email != checked["to"]:
            raise DomainError(
                "recipient_mismatch", "The recipient must match the selected contact."
            )
    if kind in {"calendar_update", "calendar_delete"}:
        require(db, Appointment, checked["appointment_id"])
        if kind == "calendar_update" and not checked.get("event"):
            raise DomainError("invalid_action", "An updated event is required.")
        if checked.get("event"):
            validate_refs(db, checked["event"])
    return checked


def propose(
    db: Session, actor: Principal, data: ActionInput, dedupe: str | None = None
) -> AIAction:
    actor.require("write")
    if dedupe:
        existing = db.scalar(select(AIAction).where(AIAction.dedupe_key == dedupe))
        if existing:
            return existing
    payload = checked_payload(db, data.kind, data.payload, data.contact_id)
    action = AIAction(
        org_id=actor.org_id,
        **data.model_dump(exclude={"payload"}),
        payload=payload,
        permission="approval_required" if data.kind in EXTERNAL_KINDS else "suggested",
        dedupe_key=dedupe,
        expires_at=now() + timedelta(days=14),
    )
    db.add(action)
    db.flush()
    audit(db, actor, "action.proposed", action.id, {"kind": action.kind})
    return action


def snapshot(action: AIAction) -> str:
    content = {"kind": action.kind, "payload": action.payload, "contact_id": action.contact_id}
    if action.approval_basis is not None:
        content["approval_basis"] = action.approval_basis
    return digest(json.dumps(content, sort_keys=True))


def decide(db: Session, actor: Principal, action_id: str, decision: Decision) -> AIAction:
    actor.require("approve")
    action = require(db, AIAction, action_id)
    if action.version != decision.version:
        raise DomainError(
            "version_conflict", "This suggestion changed. Refresh before reviewing it.", 409
        )
    if action.kind in EXTERNAL_KINDS:
        actor.require("external")
    changed = db.execute(
        update(AIAction)
        .where(AIAction.id == action_id, AIAction.version == decision.version)
        .values(version=decision.version + 1)
    )
    if changed.rowcount != 1:  # type: ignore[attr-defined]
        raise DomainError(
            "version_conflict", "Another reviewer already changed this suggestion.", 409
        )
    db.refresh(action)
    if decision.decision == "undo":
        undo(db, actor, action)
    elif decision.decision == "retry":
        if action.status != "failed":
            raise DomainError(
                "invalid_transition", "Only a definitively failed action can be retried.", 409
            )
        action.status = "pending"
        action.error_code = None
        action.approved_by = None
        action.approved_hash = None
        action.approval_basis = None
        action.expires_at = now() + timedelta(days=14)
    else:
        if action.status not in {"pending", "snoozed"}:
            raise DomainError(
                "invalid_transition", "This suggestion can no longer be changed.", 409
            )
        if decision.decision == "edit":
            if decision.payload is None:
                raise DomainError("invalid_action", "Provide an edited action.")
            action.payload = checked_payload(db, action.kind, decision.payload, action.contact_id)
            action.approval_basis = None
            action.status = "pending"
        elif decision.decision == "reject":
            action.status = "rejected"
        elif decision.decision == "snooze":
            if not decision.scheduled_at or decision.scheduled_at <= now():
                raise DomainError("invalid_time", "Choose a future time.")
            action.status, action.scheduled_at = "snoozed", decision.scheduled_at
        elif decision.decision == "approve":
            if action.expires_at and action.expires_at <= now():
                raise DomainError(
                    "expired_action", "This suggestion expired. Generate a new one.", 409
                )
            if action.kind == "crm_update":
                preference = locked_preference(db, action.payload["contact_id"])
                defaults = PreferenceInput.model_validate({}).model_dump()
                action.approval_basis = {
                    key: getattr(preference, key) if preference else defaults[key]
                    for key in action.payload["changes"]
                }
            checked_payload(db, action.kind, action.payload, action.contact_id)
            action.approved_hash, action.approved_by = snapshot(action), actor.user_id
            action.status = "approved"
            action.scheduled_at = decision.scheduled_at or now()
            db.add(
                Job(
                    org_id=actor.org_id,
                    kind="execute_action",
                    payload={"action_id": action.id, "approval_version": action.version},
                    dedupe_key=f"action:{action.id}:v{action.version}",
                    available_at=action.scheduled_at,
                )
            )
    audit(db, actor, "action." + decision.decision, action.id, {"version": action.version})
    return action


def execute(db: Session, action_id: str) -> AIAction:
    action = require(db, AIAction, action_id)
    if action.status in {"succeeded", "undone", "uncertain", "failed"}:
        return action
    if (
        action.status != "approved"
        or not action.approved_by
        or action.approved_hash != snapshot(action)
    ):
        raise DomainError("not_approved", "The action does not have a valid approval.", 409)
    if action.scheduled_at and action.scheduled_at > now():
        raise DomainError("not_due", "The approved action is scheduled for later.", 409)
    if action.expires_at and action.expires_at <= now():
        raise DomainError("expired_action", "The approval expired before execution.", 409)
    membership = db.scalar(select(Membership).where(Membership.user_id == action.approved_by))
    if not membership:
        raise DomainError("forbidden", "The approving user no longer has access.", 403)
    actor = Principal(action.approved_by, action.org_id, membership.role)
    actor.require("approve")
    if action.kind in EXTERNAL_KINDS:
        actor.require("external")
    checked_payload(db, action.kind, action.payload, action.contact_id)
    changed = db.execute(
        update(AIAction)
        .where(AIAction.id == action.id, AIAction.status == "approved")
        .values(status="executing")
    )
    if changed.rowcount != 1:  # type: ignore[attr-defined]
        raise DomainError("already_executing", "Another worker is executing this action.", 409)
    db.refresh(action)
    # External requests cannot share a database transaction. Persist the claim first.
    # Crash recovery marks an abandoned external claim uncertain; it never resends blindly.
    if action.kind in EXTERNAL_KINDS:
        db.commit()
    try:
        if action.kind == "crm_update":
            payload = CRMUpdate.model_validate(action.payload)
            preference = locked_preference(db, payload.contact_id)
            defaults = PreferenceInput.model_validate({}).model_dump()
            if action.approval_basis is None or any(
                (getattr(preference, key) if preference else defaults[key]) != value
                for key, value in action.approval_basis.items()
            ):
                raise DomainError(
                    "changed_since_approval",
                    "The reviewed preferences changed. Review a fresh suggestion before applying it.",
                    409,
                )
            if not preference:
                preference = Preference(org_id=actor.org_id, contact_id=payload.contact_id)
                db.add(preference)
                db.flush()
            changes = payload.changes.model_dump(exclude_unset=True)
            previous = {k: getattr(preference, k) for k in changes}
            merged = {k: getattr(preference, k) for k in type(payload.changes).model_fields}
            try:
                PreferenceInput.model_validate({**merged, **changes})
            except ValidationError as exc:
                raise DomainError(
                    "changed_since_approval",
                    "The change conflicts with the current preferences. Review it again.",
                    409,
                ) from exc
            for key, value in changes.items():
                setattr(preference, key, value)
                db.add(
                    Fact(
                        org_id=actor.org_id,
                        contact_id=payload.contact_id,
                        field=key,
                        value=value,
                        confidence=action.confidence,
                        state="confirmed",
                        source_type="approved_action",
                        source_id=action.id,
                        method="human_review",
                        verified_by=actor.user_id,
                    )
                )
            action.result = {
                "previous": previous,
                "applied": changes,
                "contact_id": payload.contact_id,
            }
        elif action.kind == "create_task":
            values = TaskInput.model_validate(action.payload).model_dump()
            task = Task(org_id=actor.org_id, **values, source_id=action.id)
            db.add(task)
            db.flush()
            action.result = {"task_id": task.id}
        else:
            from realty.google import execute_external

            action.result = execute_external(db, actor, action)
        action.status = "succeeded"
        db.add(
            Activity(
                org_id=actor.org_id,
                contact_id=action.contact_id,
                kind="ai_action",
                title=action.title,
                body=action.reason,
                source_id=action.id,
            )
        )
        db.add(Usage(org_id=actor.org_id, metric="automated_actions", source_id=action.id))
        audit(db, actor, "action.executed", action.id, {"kind": action.kind})
    except DomainError as exc:
        if exc.code == "google_reconnect":
            from realty.google import persist_connection_failure

            persist_connection_failure(db)
        action.status = "uncertain" if exc.code == "external_uncertain" else "failed"
        action.error_code = exc.code
        audit(db, actor, "action.execution_failed", action.id, {"code": exc.code}, action.status)
    return action


def undo(db: Session, actor: Principal, action: AIAction) -> None:
    if action.status != "succeeded" or action.kind in EXTERNAL_KINDS or not action.result:
        raise DomainError("not_reversible", "This action cannot be undone here.", 409)
    if action.kind == "create_task":
        task = require(db, Task, action.result["task_id"])
        if task.status != "open" or task.updated_at > action.updated_at:
            raise DomainError(
                "changed_since_action", "The task has changed since this action.", 409
            )
        task.status = "cancelled"
    elif action.kind == "crm_update":
        preference = locked_preference(db, action.result["contact_id"])
        if not preference or any(
            getattr(preference, k) != v for k, v in action.result["applied"].items()
        ):
            raise DomainError(
                "changed_since_action", "The profile has changed since this action.", 409
            )
        current = {key: getattr(preference, key) for key in PreferenceInput.model_fields}
        try:
            PreferenceInput.model_validate({**current, **action.result["previous"]})
        except ValidationError as exc:
            raise DomainError(
                "changed_since_action",
                "Restoring these values would conflict with the current profile.",
                409,
            ) from exc
        for key, value in action.result["previous"].items():
            setattr(preference, key, value)
        for fact in db.scalars(select(Fact).where(Fact.source_id == action.id)).all():
            fact.state = "retracted"
    action.status = "undone"
    db.add(
        Activity(
            org_id=actor.org_id,
            contact_id=action.contact_id,
            kind="undo",
            title="Undid: " + action.title,
            source_id=action.id,
        )
    )
