from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from realty import actions, billing, documents, google
from realty.db import get_db, now
from realty.errors import DomainError
from realty.intelligence import Answer, analyze_email, briefing, command, invoke
from realty.jobs import enqueue
from realty.models import (
    AIAction,
    Audit,
    Communication,
    Deal,
    Document,
    Integration,
    Job,
    Notification,
    Subscription,
    Usage,
    Workflow,
)
from realty.repository import paginate, public, require
from realty.schemas import ActionInput, Decision, WorkflowInput
from realty.schemas import Query as CommandQuery
from realty.security import Principal, audit, principal

router = APIRouter(tags=["Intelligence and operations"])


@router.get("/briefing")
def daily(
    actor: Principal = Depends(principal), db: Session = Depends(get_db, scope="function")
) -> dict[str, Any]:
    return briefing(db)


@router.post("/command")
def ask(
    body: CommandQuery,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    return command(db, actor, body.question)


@router.get("/actions")
def action_list(
    status: str | None = None,
    page: int = Query(1, ge=1),
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    statement = select(AIAction)
    if status:
        statement = statement.where(AIAction.status == status)
    return paginate(db, statement.order_by(AIAction.created_at.desc()), page, 25)


@router.post("/actions", status_code=201)
def action_create(
    body: ActionInput,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    return public(actions.propose(db, actor, body))


@router.post("/actions/{action_id}/decision")
def action_decision(
    action_id: str,
    body: Decision,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    return public(actions.decide(db, actor, action_id, body))


@router.get("/inbox")
def inbox(
    page: int = Query(1, ge=1),
    q: str = Query("", max_length=200),
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    statement = select(Communication)
    if q:
        statement = statement.where(Communication.subject.ilike("%" + q + "%"))
    return paginate(db, statement.order_by(Communication.received_at.desc()), page, 25)


@router.post("/inbox/{message_id}/analyze")
def analyze(
    message_id: str,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    actor.require("write")
    result = analyze_email(db, actor, require(db, Communication, message_id))
    return {"actions": [public(a) for a in result]}


@router.get("/integrations")
def integrations(
    actor: Principal = Depends(principal), db: Session = Depends(get_db, scope="function")
) -> dict[str, Any]:
    from realty.config import settings

    connections = db.scalars(select(Integration).where(Integration.user_id == actor.user_id)).all()
    return {
        "google_configured": google.configured(),
        "ai_configured": settings.ai_provider == "openai" and bool(settings.ai_api_key),
        "billing_configured": billing.configured(),
        "connections": [public(c) for c in connections],
        "demo_mode": settings.demo_mode,
        "call_intelligence": "not_configured",
        "ocr": "not_configured",
    }


@router.post("/integrations/google/authorize")
def google_authorize(
    capability: str = "read",
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, str]:
    return {"url": google.authorize(db, actor, capability)}


@router.get("/integrations/google/callback")
def google_callback(
    code: str = "",
    state: str = "",
    error: str = "",
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> RedirectResponse:
    from realty.config import settings

    if error:
        raise DomainError("google_denied", "Google access was not granted.")
    google.callback(db, actor, code, state)
    return RedirectResponse(settings.app_origin + "/settings?google=connected", status_code=303)


@router.post("/integrations/google/disconnect")
def google_disconnect(
    actor: Principal = Depends(principal), db: Session = Depends(get_db, scope="function")
) -> dict[str, bool]:
    google.disconnect(db, actor)
    return {"ok": True}


@router.post("/integrations/google/sync")
def google_sync(
    resource: str = "gmail",
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    actor.require("external")
    google.GoogleClient(db, actor)  # fail clearly before queuing when disconnected or unconfigured
    if resource not in {"gmail", "calendar"}:
        raise DomainError("invalid_resource", "Select Gmail or Calendar.")
    job = enqueue(
        db,
        actor.org_id,
        resource + "_sync",
        {"user_id": actor.user_id},
        f"manual:{resource}:{actor.user_id}:{now():%Y-%m-%d-%H-%M}",
    )
    return public(job)


@router.get("/integrations/google/calendars")
def calendars(
    actor: Principal = Depends(principal), db: Session = Depends(get_db, scope="function")
) -> dict[str, Any]:
    client = google.GoogleClient(db, actor)
    items, _ = google.pages(client, "calendar/v3/users/me/calendarList", {}, "items")
    return {
        "items": [
            {"id": x["id"], "summary": x.get("summary"), "access_role": x.get("accessRole")}
            for x in items
        ]
    }


@router.get("/documents")
def document_list(
    q: str = Query("", max_length=200),
    page: int = Query(1, ge=1),
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    statement = select(Document)
    if q:
        statement = statement.where(
            Document.name.ilike("%" + q + "%") | Document.text.ilike("%" + q + "%")
        )
    return paginate(db, statement.order_by(Document.created_at.desc()), page, 25)


@router.post("/documents", status_code=201)
async def document_upload(
    file: UploadFile = File(...),
    contact_id: str | None = Form(None),
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    content = await file.read(documents.MAX_UPLOAD + 1)
    document = documents.upload(db, actor, file.filename or "document", content, contact_id)
    if document.status == "pending_extraction":
        enqueue(
            db,
            actor.org_id,
            "document_extract",
            {"document_id": document.id, "user_id": actor.user_id},
            "document:" + document.id,
        )
    return public(document)


@router.get("/documents/{document_id}/download")
def document_download(
    document_id: str,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> Response:
    from urllib.parse import quote

    document = require(db, Document, document_id)
    audit(db, actor, "document.downloaded", document.id)
    return Response(
        documents.storage().get(document.storage_key),
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(document.name)},
    )


@router.post("/documents/{document_id}/summarize")
def document_summary(
    document_id: str,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    actor.require("write")
    document = require(db, Document, document_id)
    if not document.text:
        raise DomainError(
            "no_document_text",
            "This document has no extracted text. Scanned PDFs require an OCR provider.",
            409,
        )
    result = invoke(
        db,
        actor,
        "Summarize the supplied document for internal review. Do not offer legal advice. Cite its source ID.",
        {"source_id": document.id, "text": document.text[:24000]},
        Answer,
    )
    assert isinstance(result, Answer)
    if set(result.source_ids) - {document.id}:
        raise DomainError(
            "unsupported_evidence", "Document summary cited an unavailable source.", 422
        )
    document.summary = result.answer
    return public(document)


@router.delete("/documents/{document_id}")
def document_delete(
    document_id: str,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, bool]:
    actor.require("write")
    document = require(db, Document, document_id)
    documents.storage().delete(document.storage_key)
    audit(db, actor, "document.deleted", document.id)
    db.delete(document)
    return {"ok": True}


@router.get("/notifications")
def notifications(
    actor: Principal = Depends(principal), db: Session = Depends(get_db, scope="function")
) -> dict[str, Any]:
    return paginate(db, select(Notification).order_by(Notification.created_at.desc()), 1, 100)


@router.post("/notifications/{notification_id}/read")
def notification_read(
    notification_id: str,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    item = require(db, Notification, notification_id)
    item.read = True
    return public(item)


@router.get("/analytics")
def analytics(
    actor: Principal = Depends(principal), db: Session = Depends(get_db, scope="function")
) -> dict[str, Any]:
    stages = db.execute(
        select(Deal.stage, func.count(Deal.id), func.sum(Deal.value)).group_by(Deal.stage)
    ).all()
    usage = db.execute(select(Usage.metric, func.sum(Usage.quantity)).group_by(Usage.metric)).all()
    decisions = db.execute(
        select(AIAction.status, func.count(AIAction.id)).group_by(AIAction.status)
    ).all()
    return {
        "pipeline": [{"stage": s, "count": c, "value": v} for s, c, v in stages],
        "usage": [{"metric": m, "quantity": q} for m, q in usage],
        "actions": [{"status": s, "count": c} for s, c in decisions],
    }


@router.get("/audit")
def audit_list(
    page: int = Query(1, ge=1),
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    actor.require("members")
    return paginate(db, select(Audit).order_by(Audit.created_at.desc()), page, 50)


@router.get("/jobs")
def jobs(
    actor: Principal = Depends(principal), db: Session = Depends(get_db, scope="function")
) -> dict[str, Any]:
    actor.require("members")
    return paginate(db, select(Job).order_by(Job.created_at.desc()), 1, 50)


@router.post("/jobs/{job_id}/retry")
def retry_job(
    job_id: str,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    actor.require("members")
    job = require(db, Job, job_id)
    if job.status != "dead" or job.kind == "execute_action":
        raise DomainError(
            "job_not_retryable", "Review failed external actions in the action center.", 409
        )
    job.status, job.attempts, job.available_at = "queued", 0, now()
    audit(db, actor, "job.retried", job.id)
    return public(job)


@router.get("/workflows")
def workflows(
    actor: Principal = Depends(principal), db: Session = Depends(get_db, scope="function")
) -> dict[str, Any]:
    return paginate(db, select(Workflow).order_by(Workflow.name), 1, 100)


@router.post("/workflows")
def workflow_create(
    body: WorkflowInput,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    actor.require("members")
    row = Workflow(org_id=actor.org_id, **body.model_dump())
    db.add(row)
    db.flush()
    audit(db, actor, "workflow.created", row.id)
    return public(row)


@router.put("/workflows/{workflow_id}")
def workflow_update(
    workflow_id: str,
    body: WorkflowInput,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    actor.require("members")
    row = require(db, Workflow, workflow_id)
    for key, value in body.model_dump().items():
        setattr(row, key, value)
    audit(db, actor, "workflow.updated", row.id)
    return public(row)


@router.get("/billing")
def billing_state(
    actor: Principal = Depends(principal), db: Session = Depends(get_db, scope="function")
) -> dict[str, Any]:
    actor.require("billing")
    row = db.scalar(select(Subscription))
    return {"subscription": public(row) if row else None, "configured": billing.configured()}


@router.post("/billing/checkout")
def billing_checkout(
    request_id: UUID,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, str]:
    return {"url": billing.checkout(db, actor, str(request_id))}


@router.post("/billing/portal")
def billing_portal(
    actor: Principal = Depends(principal), db: Session = Depends(get_db, scope="function")
) -> dict[str, str]:
    return {"url": billing.portal(db, actor)}


@router.get("/billing/invoices")
def invoices(
    actor: Principal = Depends(principal), db: Session = Depends(get_db, scope="function")
) -> dict[str, Any]:
    subscription = billing.customer(db, actor)
    result = billing.stripe_request(
        "GET", "invoices?customer=" + (subscription.customer_id or "") + "&limit=25"
    )
    return {
        "items": [
            {
                "id": i["id"],
                "status": i["status"],
                "amount_paid": i["amount_paid"],
                "currency": i["currency"],
                "url": i.get("hosted_invoice_url"),
            }
            for i in result.get("data", [])
        ]
    }


@router.post("/webhooks/stripe", include_in_schema=False)
async def stripe_webhook(
    request: Request, db: Session = Depends(get_db, scope="function")
) -> dict[str, bool]:
    payload = await request.body()
    if len(payload) > 1_000_000:
        raise DomainError("payload_too_large", "Webhook payload exceeds limit.", 413)
    return {"processed": billing.webhook(db, payload, request.headers.get("stripe-signature", ""))}
