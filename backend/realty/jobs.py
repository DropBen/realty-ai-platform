import logging
import time
from datetime import timedelta
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from realty.actions import execute, propose
from realty.db import SessionLocal, now
from realty.errors import DomainError
from realty.intelligence import analyze_email, match_property
from realty.models import (
    AIAction,
    Communication,
    Contact,
    Document,
    Job,
    Membership,
    Notification,
    Preference,
    Property,
    Usage,
    Workflow,
)
from realty.repository import require
from realty.schemas import ActionInput
from realty.security import Principal, audit

log = logging.getLogger("realty.worker")


def enqueue(db: Session, org_id: str, kind: str, payload: dict[str, Any], dedupe: str) -> Job:
    existing = db.scalar(select(Job).where(Job.dedupe_key == dedupe))
    if existing:
        return existing
    job = Job(org_id=org_id, kind=kind, payload=payload, dedupe_key=dedupe)
    db.add(job)
    db.flush()
    return job


def emit(db: Session, actor: Principal, event: str, target: str) -> None:
    enqueue(
        db,
        actor.org_id,
        "workflow_event",
        {"event": event, "target": target, "user_id": actor.user_id},
        event + ":" + target,
    )


def followup(
    db: Session, actor: Principal, contact: Contact, dedupe: str | None = None
) -> AIAction:
    if not contact.email:
        raise DomainError(
            "missing_email", "Add a confirmed email address before drafting a follow-up."
        )
    latest = db.scalar(
        select(Communication)
        .where(Communication.contact_id == contact.id)
        .order_by(Communication.received_at.desc())
    )
    subject = "Following up" if not latest else "Re: " + latest.subject.removeprefix("Re: ")[:240]
    # Transparent editable template generated from current CRM context, without invented promises.
    body = f"Hi {contact.name.split()[0]},\n\n"
    body += (
        f"I wanted to follow up on our conversation about “{latest.subject}”. "
        if latest
        else "I wanted to check in on your real-estate plans. "
    )
    preference = db.scalar(select(Preference).where(Preference.contact_id == contact.id))
    if preference and preference.location:
        body += f"Are you still considering {preference.location}? "
    body += "What would be most helpful for you next?\n\nBest regards"
    return propose(
        db,
        actor,
        ActionInput(
            kind="send_email",
            title="Follow up with " + contact.name,
            reason="Draft prepared from the recorded relationship. Review the recipient, wording and timing before sending.",
            contact_id=contact.id,
            source_id=latest.id if latest else contact.id,
            payload={"to": contact.email, "subject": subject, "body": body},
        ),
        dedupe,
    )


def workflow_event(db: Session, actor: Principal, event: str, target: str) -> None:
    for rule in db.scalars(
        select(Workflow).where(Workflow.enabled.is_(True), Workflow.trigger == event)
    ).all():
        if event == "PROPERTY_CREATED":
            prop = require(db, Property, target)
            if rule.action == "notify":
                db.add(
                    Notification(
                        org_id=actor.org_id, title=rule.name, body=prop.address, link="/properties"
                    )
                )
                continue
            for pref in db.scalars(select(Preference).limit(1000)).all():
                result = match_property(pref, prop)
                if result["score"] and result["score"] >= 80:
                    db.add(
                        Notification(
                            org_id=actor.org_id,
                            title="A property matches a client's preferences",
                            body=prop.address,
                            link="/properties",
                        )
                    )
                    contact = require(db, Contact, pref.contact_id)
                    if contact.email:
                        reasons = ", ".join(
                            f["label"] for f in result["factors"] if f["state"] == "match"
                        )
                        propose(
                            db,
                            actor,
                            ActionInput(
                                kind="send_email",
                                contact_id=contact.id,
                                title="Share a property with " + contact.name,
                                source_id=prop.id,
                                reason=f"{result['score']}% of known criteria match: {reasons}. Verify listing details before sharing.",
                                payload={
                                    "to": contact.email,
                                    "subject": "A property to consider: " + prop.address,
                                    "body": f"Hi {contact.name.split()[0]},\n\nYou may want to consider {prop.address} in {prop.location}, listed at ${prop.price:,}. It has {prop.bedrooms} bedrooms and {prop.bathrooms:g} bathrooms. Would you like to discuss it?\n\nBest regards",
                                },
                            ),
                            f"match:{rule.id}:{prop.id}:{contact.id}",
                        )
        else:
            contact = require(db, Contact, target)
            if contact.score < rule.condition.get("min_score", 0):
                continue
            if rule.action == "recommend_followup" and contact.email:
                followup(db, actor, contact, f"workflow:{rule.id}:{event}:{target}:{now().date()}")
            else:
                db.add(
                    Notification(
                        org_id=actor.org_id,
                        title=rule.name,
                        body=contact.name,
                        link="/contacts/" + contact.id,
                    )
                )
        db.add(Usage(org_id=actor.org_id, metric="workflow_executions", source_id=rule.id))
        audit(db, actor, "workflow.executed", rule.id)


def dispatch(db: Session, job: Job) -> None:
    if job.kind == "execute_action":
        execute(db, job.payload["action_id"])
        return
    user_id = job.payload.get("user_id")
    member = db.scalar(select(Membership).where(Membership.user_id == user_id))
    if not member:
        raise DomainError("job_authorization", "The job actor no longer has access.", 403)
    actor = Principal(member.user_id, member.org_id, member.role)
    actor.require("write")
    if job.kind == "analyze_email":
        analyze_email(db, actor, require(db, Communication, job.payload["message_id"]))
    elif job.kind == "gmail_sync":
        from realty.google import sync_gmail

        sync_gmail(db, actor)
    elif job.kind == "calendar_sync":
        from realty.google import sync_calendar

        sync_calendar(db, actor, job.payload.get("calendar_id", "primary"))
    elif job.kind == "document_extract":
        from realty.documents import extract_pdf

        extract_pdf(db, require(db, Document, job.payload["document_id"]))
    elif job.kind == "workflow_event":
        workflow_event(db, actor, job.payload["event"], job.payload["target"])
    else:
        raise DomainError("unknown_job", "The job type is not supported.")


def tick() -> bool:
    """Atomic compare-and-swap claim works on SQLite and PostgreSQL without a broker."""
    with SessionLocal() as db:
        job = db.scalar(
            select(Job)
            .where(
                or_(
                    (Job.status == "queued") & (Job.available_at <= now()),
                    (Job.status == "running") & (Job.lease_until < now()),
                )
            )
            .order_by(Job.available_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if not job:
            return False
        was_running = job.status == "running"
        claimed = db.execute(
            update(Job)
            .where(Job.id == job.id, Job.status == job.status, Job.attempts == job.attempts)
            .values(
                status="running",
                attempts=job.attempts + 1,
                lease_until=now() + timedelta(minutes=10),
            )
        )
        if claimed.rowcount != 1:  # type: ignore[attr-defined]
            db.rollback()
            return False
        db.commit()
        db.refresh(job)
        db.info["org_id"] = job.org_id
        if was_running and job.kind == "execute_action":
            action = require(db, AIAction, job.payload["action_id"])
            if action.status == "executing":
                action.status, action.error_code = "uncertain", "worker_interrupted"
                job.status = "dead"
                db.add(
                    Notification(
                        org_id=job.org_id,
                        title="Review an interrupted external action",
                        body="The provider may have completed it. Verify before creating another action.",
                    )
                )
                db.commit()
                return True
        try:
            dispatch(db, job)
            job.status, job.error_code = "done", None
            db.commit()
        except Exception as exc:
            db.rollback()
            db.refresh(job)
            code = exc.code if isinstance(exc, DomainError) else "internal_error"
            if job.kind == "execute_action":
                action = require(db, AIAction, job.payload["action_id"])
                if action.status == "executing":
                    action.status, action.error_code = "uncertain", "execution_interrupted"
                    code = "external_uncertain"
            job.error_code = code
            job.status = (
                "dead"
                if job.attempts >= 5
                or code
                in {
                    "external_uncertain",
                    "ai_unconfigured",
                    "google_unconfigured",
                    "job_authorization",
                    "not_approved",
                }
                else "queued"
            )
            job.available_at = now() + timedelta(seconds=min(900, 15 * 2**job.attempts))
            log.warning("job.failed", extra={"job_id": job.id, "org_id": job.org_id, "code": code})
            db.commit()
        return True


def schedule_recurring() -> None:
    """Hourly sweep creates idempotent follow-up and connected-account sync jobs."""
    from realty.models import Integration, Organization

    with SessionLocal() as discovery:
        ids = list(discovery.scalars(select(Organization.id)).all())
    for org_id in ids:
        with SessionLocal() as db:
            db.info["org_id"] = org_id
            owner = db.scalar(select(Membership).where(Membership.role == "owner"))
            if not owner:
                continue
            actor = Principal(owner.user_id, org_id, owner.role)
            for contact in db.scalars(
                select(Contact)
                .where(
                    Contact.archived.is_(False),
                    Contact.email.is_not(None),
                    or_(
                        Contact.last_contact_at.is_(None),
                        Contact.last_contact_at < now() - timedelta(days=7),
                    ),
                )
                .limit(1000)
            ).all():
                enqueue(
                    db,
                    org_id,
                    "workflow_event",
                    {"event": "FOLLOW_UP_REQUIRED", "target": contact.id, "user_id": actor.user_id},
                    f"followup:{contact.id}:{now().date()}",
                )
            for connection in db.scalars(
                select(Integration).where(Integration.status == "connected")
            ).all():
                for kind in ["gmail_sync", "calendar_sync"]:
                    enqueue(
                        db,
                        org_id,
                        kind,
                        {"user_id": connection.user_id},
                        f"{kind}:{connection.id}:{now():%Y-%m-%d-%H}",
                    )
            db.commit()


def main() -> None:
    last_sweep = 0.0
    while True:
        if time.monotonic() - last_sweep > 3600:
            schedule_recurring()
            last_sweep = time.monotonic()
        if not tick():
            time.sleep(2)


if __name__ == "__main__":
    main()
