from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import stripe
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from realty.config import settings
from realty.db import now
from realty.errors import DomainError
from realty.models import Organization, Subscription, WebhookEvent
from realty.repository import insert_for
from realty.security import Principal, audit, require_live_organization


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
        value = response.json()
        if not isinstance(value, dict):
            raise ValueError("Expected a provider object")
        return value
    except (httpx.HTTPError, ValueError) as exc:
        raise DomainError(
            "billing_unavailable", "Billing is temporarily unavailable. Try again later.", 502
        ) from exc


def customer(db: Session, actor: Principal) -> Subscription:
    actor.require("billing")
    require_live_organization(db, actor.org_id)
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
    customer(db, actor)
    subscription = locked_subscription(db)
    terminal_subscription = None
    if subscription.subscription_id:
        current = stripe_request("GET", "subscriptions/" + subscription.subscription_id)
        if (
            current.get("id") != subscription.subscription_id
            or current.get("customer") != subscription.customer_id
        ):
            raise DomainError(
                "billing_identity_mismatch", "The current subscription could not be verified.", 502
            )
        if current.get("status") not in {"canceled", "incomplete_expired"}:
            return portal(db, actor)
        terminal_subscription = subscription.subscription_id
    pending = subscription.checkout_state
    if pending and pending.get("session_id"):
        existing = stripe_request("GET", "checkout/sessions/" + pending["session_id"])
        validate_checkout(existing, subscription.customer_id)
        if existing["id"] != pending["session_id"]:
            raise DomainError("billing_identity_mismatch", "The checkout identity changed.", 502)
        if existing["status"] == "open":
            return checkout_url(existing)
        if existing["status"] == "complete" and (
            not terminal_subscription or existing.get("subscription") != terminal_subscription
        ):
            return portal(db, actor)
        pending = None  # Provider-confirmed expiration/cancellation permits a new checkout.
    if not pending:
        parameters = {
            "mode": "subscription",
            "customer": subscription.customer_id or "",
            "line_items[0][price]": settings.stripe_price_id,
            "line_items[0][quantity]": "1",
            "client_reference_id": actor.org_id,
            "subscription_data[metadata][org_id]": actor.org_id,
            "success_url": settings.app_origin + "/billing?checkout=complete",
            "cancel_url": settings.app_origin + "/billing?checkout=cancelled",
        }
        pending = {
            "key": "checkout:" + actor.org_id + ":" + request_id,
            "created_at": now().isoformat(),
            "parameters": parameters,
        }
        subscription.checkout_state = pending
        db.commit()  # Preserve the exact attempt and parameters across timeouts/crashes.
    if datetime.fromisoformat(pending["created_at"]) < now() - timedelta(hours=23):
        raise DomainError(
            "billing_checkout_reconcile",
            "A previous checkout could not be confirmed. Reconcile its Stripe request before starting another.",
            409,
        )
    result = stripe_request("POST", "checkout/sessions", pending["parameters"], pending["key"])
    validate_checkout(result, subscription.customer_id)
    subscription = locked_subscription(db)
    if not subscription.checkout_state or subscription.checkout_state["key"] != pending["key"]:
        raise DomainError(
            "billing_checkout_changed", "Checkout changed. Refresh billing to continue.", 409
        )
    subscription.checkout_state = {**pending, "session_id": result["id"]}
    audit(db, actor, "billing.checkout_created")
    if result["status"] == "complete":
        return portal(db, actor)
    if result["status"] == "expired":
        db.commit()
        raise DomainError(
            "billing_checkout_expired", "This checkout expired. Start checkout again.", 409
        )
    return checkout_url(result)


def locked_subscription(db: Session) -> Subscription:
    if db.get_bind().dialect.name == "sqlite":
        db.execute(update(Subscription).values(updated_at=Subscription.updated_at))
    subscription = db.scalar(
        select(Subscription).with_for_update().execution_options(populate_existing=True)
    )
    if not subscription:
        raise DomainError("billing_missing", "Subscription record is unavailable.", 409)
    return subscription


def validate_checkout(value: dict[str, Any], customer_id: str | None) -> None:
    if (
        not isinstance(value.get("id"), str)
        or not value["id"]
        or value.get("customer") != customer_id
    ):
        raise DomainError(
            "billing_identity_mismatch", "The checkout customer could not be verified.", 502
        )
    if value.get("status") not in {"open", "complete", "expired"}:
        raise DomainError(
            "billing_invalid_response", "The checkout state could not be verified.", 502
        )


def checkout_url(value: dict[str, Any]) -> str:
    url = value.get("url")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise DomainError(
            "billing_invalid_response", "The checkout URL could not be verified.", 502
        )
    return url


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
    receipt = db.scalar(
        insert_for(db, WebhookEvent)
        .values(id=event["id"])
        .on_conflict_do_nothing(index_elements=[WebhookEvent.id])
        .returning(WebhookEvent.id)
    )
    if receipt is None:
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
    require_live_organization(db, subscription.org_id)
    if event["created"] < subscription.last_event_created:
        return True
    # Read canonical provider state so reordered same-second events cannot regress entitlements.
    current = stripe_request("GET", "subscriptions/" + data["id"])
    if current.get("id") != data["id"] or current.get("customer") != subscription.customer_id:
        raise DomainError(
            "billing_identity_mismatch", "The subscription identity could not be verified.", 502
        )
    if current.get("status") not in {
        "active",
        "trialing",
        "past_due",
        "canceled",
        "unpaid",
        "incomplete",
        "incomplete_expired",
        "paused",
    }:
        raise DomainError(
            "billing_invalid_response", "The subscription status could not be validated.", 502
        )
    terminal = {"canceled", "incomplete_expired"}
    if subscription.subscription_id and subscription.subscription_id != current["id"]:
        if current["status"] in terminal:
            # A late cancellation for a previous subscription must not cancel its replacement.
            audit(
                db,
                Principal("stripe", subscription.org_id, "owner"),
                "billing.unrelated_terminal_event",
                subscription.id,
                {"event_id": event["id"]},
            )
            return True
        tracked = stripe_request("GET", "subscriptions/" + subscription.subscription_id)
        if (
            tracked.get("id") != subscription.subscription_id
            or tracked.get("customer") != subscription.customer_id
        ):
            raise DomainError(
                "billing_identity_mismatch",
                "The existing subscription identity could not be verified.",
                502,
            )
        if tracked.get("status") not in terminal:
            # Never silently choose between two potentially billable subscriptions.
            # Roll back the receipt so reconciliation permits a provider redelivery.
            raise DomainError(
                "billing_subscription_conflict",
                "Another subscription is still open for this workspace. Reconcile it in Stripe before applying a replacement.",
                409,
            )
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
