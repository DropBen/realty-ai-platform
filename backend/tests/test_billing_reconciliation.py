import json

import pytest
from realty import billing
from realty.config import settings
from realty.errors import DomainError
from realty.models import Subscription, WebhookEvent
from realty.security import Principal
from sqlalchemy import select
from test_integrations import signature


@pytest.fixture
def checkout_setup(account, factory, monkeypatch, live_account):
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "stripe_price_id", "price_test")
    actor = Principal(account["user"]["id"], account["organization"]["id"], "owner")
    with factory() as db:
        db.scalar(select(Subscription)).customer_id = "cus_test"
        db.commit()
    return actor


def test_checkout_reuses_open_session_and_does_not_double_charge_before_webhook(
    checkout_setup, factory, monkeypatch
):
    calls = []
    session = {
        "id": "cs_test",
        "customer": "cus_test",
        "status": "open",
        "url": "https://checkout.stripe.com/example",
    }

    def request(method, path, *args):
        calls.append((method, path, args))
        return (
            {"url": "https://billing.stripe.com/portal"}
            if path == "billing_portal/sessions"
            else session
        )

    monkeypatch.setattr(billing, "stripe_request", request)
    with factory() as db:
        db.info["org_id"] = checkout_setup.org_id
        assert billing.checkout(db, checkout_setup, "first") == session["url"]
        db.commit()
        assert billing.checkout(db, checkout_setup, "second") == session["url"]
        db.commit()
        session["status"] = "complete"
        assert billing.checkout(db, checkout_setup, "third") == "https://billing.stripe.com/portal"
    assert sum(method == "POST" and path == "checkout/sessions" for method, path, _ in calls) == 1


def test_checkout_timeout_reuses_exact_persisted_attempt(checkout_setup, factory, monkeypatch):
    attempts = []

    def request(method, path, data, key):
        attempts.append((data.copy(), key))
        if len(attempts) == 1:
            raise DomainError("billing_unavailable", "Simulated response loss", 502)
        return {
            "id": "cs_test",
            "customer": "cus_test",
            "status": "open",
            "url": "https://checkout.stripe.com/example",
        }

    monkeypatch.setattr(billing, "stripe_request", request)
    with factory() as db:
        db.info["org_id"] = checkout_setup.org_id
        with pytest.raises(DomainError):
            billing.checkout(db, checkout_setup, "first")
        db.rollback()
    monkeypatch.setattr(settings, "stripe_price_id", "price_changed")
    with factory() as db:
        db.info["org_id"] = checkout_setup.org_id
        billing.checkout(db, checkout_setup, "different-browser-request")
        db.commit()
    assert len(attempts) == 2 and attempts[0] == attempts[1]


def test_unresolved_old_checkout_cannot_be_replayed_after_idempotency_retention(
    checkout_setup, factory, monkeypatch
):
    from datetime import timedelta

    from realty.db import now

    def unexpected(*args):
        pytest.fail("An ambiguous old attempt must not create another provider checkout")

    monkeypatch.setattr(billing, "stripe_request", unexpected)
    with factory() as db:
        db.info["org_id"] = checkout_setup.org_id
        subscription = db.scalar(select(Subscription))
        subscription.checkout_state = {
            "key": "old",
            "created_at": (now() - timedelta(days=2)).isoformat(),
            "parameters": {},
        }
        db.commit()
        with pytest.raises(DomainError) as error:
            billing.checkout(db, checkout_setup, "new")
        assert error.value.code == "billing_checkout_reconcile"


def test_expired_checkout_allows_new_attempt(checkout_setup, factory, monkeypatch):
    calls = []

    def request(method, path, *args):
        calls.append((method, path))
        return {
            "id": "cs_old" if method == "GET" else "cs_new",
            "customer": "cus_test",
            "status": "expired" if method == "GET" else "open",
            "url": "https://checkout.stripe.com/new",
        }

    monkeypatch.setattr(billing, "stripe_request", request)
    with factory() as db:
        db.info["org_id"] = checkout_setup.org_id
        db.scalar(select(Subscription)).checkout_state = {"key": "old", "session_id": "cs_old"}
        db.commit()
        assert billing.checkout(db, checkout_setup, "new") == "https://checkout.stripe.com/new"
        db.commit()
    assert calls == [("GET", "checkout/sessions/cs_old"), ("POST", "checkout/sessions")]


@pytest.mark.parametrize("canonical_status", ["active", "canceled"])
def test_resubscribe_requires_provider_confirmed_cancellation(
    checkout_setup, factory, monkeypatch, canonical_status
):
    calls = []

    def request(method, path, *args):
        calls.append((method, path))
        if path == "subscriptions/sub_old":
            return {"id": "sub_old", "customer": "cus_test", "status": canonical_status}
        if path == "billing_portal/sessions":
            return {"url": "https://billing.stripe.com/portal"}
        return {
            "id": "cs_old" if method == "GET" else "cs_new",
            "customer": "cus_test",
            "status": "complete" if method == "GET" else "open",
            "subscription": "sub_old" if method == "GET" else None,
            "url": "https://checkout.stripe.com/new",
        }

    monkeypatch.setattr(billing, "stripe_request", request)
    with factory() as db:
        db.info["org_id"] = checkout_setup.org_id
        row = db.scalar(select(Subscription))
        row.subscription_id, row.status = "sub_old", "canceled"
        row.checkout_state = {"key": "old", "session_id": "cs_old"}
        db.commit()
        result = billing.checkout(db, checkout_setup, "new")
        if canonical_status == "active":
            assert result == "https://billing.stripe.com/portal"
            assert ("POST", "checkout/sessions") not in calls
        else:
            assert result == "https://checkout.stripe.com/new"
            assert calls.count(("POST", "checkout/sessions")) == 1


@pytest.mark.parametrize("current_status", ["active", "canceled"])
def test_old_subscription_events_do_not_replace_current_subscription(
    account, factory, monkeypatch, current_status, live_account
):
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "stripe_webhook_secret", "test-webhook")
    monkeypatch.setattr(settings, "stripe_price_id", "price_test")
    monkeypatch.setattr(
        billing,
        "stripe_request",
        lambda method, path: {
            "id": path.split("/")[-1],
            "customer": "cus_test",
            "status": "canceled" if path.endswith("sub_old") else current_status,
            "items": {"data": [{"price": {"id": "price_test"}}]},
        },
    )
    with factory() as db:
        subscription = db.scalar(select(Subscription))
        subscription.customer_id = "cus_test"
        subscription.subscription_id = "sub_current"
        subscription.status = current_status
        subscription.plan = "professional"
        subscription.last_event_created = 100
        db.commit()
        body = json.dumps(
            {
                "id": "evt_old",
                "type": "customer.subscription.deleted",
                "created": 200,
                "data": {"object": {"id": "sub_old", "customer": "cus_test"}},
            }
        ).encode()
        assert billing.webhook(db, body, signature(body, "test-webhook"))
        db.commit()
        assert (subscription.subscription_id, subscription.status) == (
            "sub_current",
            current_status,
        )
        assert subscription.last_event_created == 100


@pytest.mark.parametrize("tracked_status", ["active", "canceled"])
def test_replacement_subscription_requires_canonical_terminal_predecessor(
    account, factory, monkeypatch, tracked_status, live_account
):
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "stripe_webhook_secret", "test-webhook")
    monkeypatch.setattr(settings, "stripe_price_id", "price_test")
    monkeypatch.setattr(
        billing,
        "stripe_request",
        lambda method, path: {
            "id": path.split("/")[-1],
            "customer": "cus_test",
            "status": tracked_status if path.endswith("sub_current") else "active",
            "items": {"data": [{"price": {"id": "price_test"}}]},
        },
    )
    with factory() as db:
        subscription = db.scalar(select(Subscription))
        subscription.customer_id = "cus_test"
        subscription.subscription_id = "sub_current"
        subscription.status = "canceled"  # Deliberately stale local data is not authority.
        db.commit()
        body = json.dumps(
            {
                "id": "evt_new",
                "type": "customer.subscription.created",
                "created": 200,
                "data": {"object": {"id": "sub_new", "customer": "cus_test"}},
            }
        ).encode()
        if tracked_status == "active":
            with pytest.raises(DomainError) as error:
                billing.webhook(db, body, signature(body, "test-webhook"))
            assert error.value.code == "billing_subscription_conflict"
            db.rollback()
            assert subscription.subscription_id == "sub_current"
            assert db.get(WebhookEvent, "evt_new") is None
        else:
            assert billing.webhook(db, body, signature(body, "test-webhook"))
            db.commit()
            assert (subscription.subscription_id, subscription.status) == ("sub_new", "active")
