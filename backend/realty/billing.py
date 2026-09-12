from datetime import UTC, datetime
from typing import Any

import httpx
import stripe
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from realty.config import settings
from realty.errors import DomainError
from realty.models import Organization, Subscription, WebhookEvent
from realty.security import Principal, audit


def configured() -> bool:
    return bool(settings.stripe_secret_key and settings.stripe_price_id and not settings.demo_mode)


def stripe_request(
    method: str, path: str, data: dict[str, str] | None = None, key: str | None = None
) -> dict[str, Any]:
    if not configured():
        raise DomainError("billing_unconfigured", "Billing integration is not configured.", 503)
    headers = {"Authorization": "Bearer " + settings.stripe_secret_key}
    if key:
        headers["Idempotency-Key"] = key
    try:
        response = httpx.request(
            method, "https://api.stripe.com/v1/" + path, data=data, headers=headers, timeout=20
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]
    except (httpx.HTTPError, ValueError) as exc:
        raise DomainError(
            "billing_unavailable", "Billing is temporarily unavailable. Try again later.", 502
        ) from exc


def customer(db: Session, actor: Principal) -> Subscription:
    actor.require("billing")
    subscription = db.scalar(select(Subscription).with_for_update())
    if not subscription:
        raise DomainError("billing_missing", "Subscription record is unavailable.", 409)
    if not subscription.customer_id:
        org = db.get(Organization, actor.org_id)
        result = stripe_request(
            "POST",
            "customers",
            {"name": org.name if org else "RealtyAI", "metadata[org_id]": actor.org_id},
            "customer:" + actor.org_id,
        )
        subscription.customer_id = result["id"]
        db.commit()
    return subscription


def checkout(db: Session, actor: Principal, request_id: str) -> str:
    subscription = customer(db, actor)
    if subscription.subscription_id and subscription.status in {"active", "trialing", "past_due"}:
        return portal(db, actor)
    result = stripe_request(
        "POST",
        "checkout/sessions",
        {
            "mode": "subscription",
            "customer": subscription.customer_id or "",
            "line_items[0][price]": settings.stripe_price_id,
            "line_items[0][quantity]": "1",
            "client_reference_id": actor.org_id,
            "subscription_data[metadata][org_id]": actor.org_id,
            "success_url": settings.app_origin + "/billing?checkout=complete",
            "cancel_url": settings.app_origin + "/billing?checkout=cancelled",
        },
        "checkout:" + actor.org_id + ":" + request_id,
    )
    audit(db, actor, "billing.checkout_created")
    return str(result["url"])


def portal(db: Session, actor: Principal) -> str:
    subscription = customer(db, actor)
    result = stripe_request(
        "POST",
        "billing_portal/sessions",
        {
            "customer": subscription.customer_id or "",
            "return_url": settings.app_origin + "/billing",
        },
    )
    return str(result["url"])


def webhook(db: Session, payload: bytes, signature: str) -> bool:
    if not settings.stripe_webhook_secret or settings.demo_mode:
        raise DomainError("billing_unconfigured", "Billing webhook is not configured.", 503)
    try:
        event = stripe.Webhook.construct_event(
            payload, signature, settings.stripe_webhook_secret, tolerance=300
        )
    except (ValueError, stripe.SignatureVerificationError) as exc:
        raise DomainError("invalid_signature", "Invalid webhook signature.", 400) from exc
    try:
        with db.begin_nested():
            db.add(WebhookEvent(id=event["id"]))
            db.flush()
    except IntegrityError:
        return False
    if event["type"] not in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }:
        return True
    data = event["data"]["object"]
    subscription = db.scalar(
        select(Subscription).where(Subscription.customer_id == data["customer"]).with_for_update()
    )
    if not subscription:
        # Fail, roll back event insertion and permit provider redelivery after customer setup.
        raise DomainError("unknown_customer", "Subscription customer has not been registered.", 409)
    db.info["org_id"] = subscription.org_id
    if event["created"] < subscription.last_event_created:
        return True
    # Read canonical provider state so reordered same-second events cannot regress entitlements.
    current = stripe_request("GET", "subscriptions/" + data["id"])
    subscription.last_event_created = event["created"]
    subscription.subscription_id = current["id"]
    subscription.status = current["status"]
    prices = [i.get("price", {}).get("id") for i in current.get("items", {}).get("data", [])]
    subscription.plan = "professional" if settings.stripe_price_id in prices else "unrecognized"
    if subscription.plan == "unrecognized":
        subscription.status = "restricted"
    period = current.get("current_period_end") or next(
        (i.get("current_period_end") for i in current.get("items", {}).get("data", [])), None
    )
    subscription.period_end = (
        datetime.fromtimestamp(period, UTC).replace(tzinfo=None) if period else None
    )
    subscription.cancel_at_period_end = current.get("cancel_at_period_end", False)
    audit(
        db,
        Principal("stripe", subscription.org_id, "owner"),
        "billing.updated",
        subscription.id,
        {"status": subscription.status, "event_id": event["id"]},
    )
    return True
