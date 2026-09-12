import base64
import hashlib
import hmac
import json
import time
from datetime import timedelta

import httpx
import pytest
import respx
from cryptography.fernet import Fernet
from realty import billing, google
from realty.config import settings
from realty.db import now
from realty.errors import DomainError
from realty.intelligence import Answer, OpenAIProvider
from realty.jobs import tick
from realty.models import (
    AIAction,
    Communication,
    Integration,
    Job,
    OAuthState,
    Subscription,
    SyncCursor,
)
from realty.security import Principal
from sqlalchemy import select


@pytest.fixture
def configured_google(monkeypatch, factory, account):
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "google_client_id", "test-client")
    monkeypatch.setattr(settings, "google_client_secret", "test-secret")
    with factory() as db:
        token = (
            google.cipher()
            .encrypt(
                json.dumps(
                    {
                        "access_token": "test-access",
                        "refresh_token": "test-refresh",
                        "expires_at": time.time() + 3600,
                    }
                ).encode()
            )
            .decode()
        )
        db.add(
            Integration(
                org_id=account["organization"]["id"],
                user_id=account["user"]["id"],
                email="agent-one@example.com",
                token_ciphertext=token,
                scopes=" ".join(google.SCOPES["read"]),
            )
        )
        db.commit()
    return Principal(account["user"]["id"], account["organization"]["id"], "owner")


def test_oauth_state_is_bound_single_use_and_tokens_encrypted(
    client, account, factory, monkeypatch
):
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "google_client_id", "test-client")
    monkeypatch.setattr(settings, "google_client_secret", "test-secret")
    from urllib.parse import parse_qs, urlparse

    response = client.post("/api/v1/integrations/google/authorize")
    assert response.status_code == 200
    params = parse_qs(urlparse(response.json()["url"]).query)
    assert params["code_challenge_method"] == ["S256"]
    state = params["state"][0]
    with respx.mock:
        respx.post("https://oauth2.googleapis.com/token").mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "never-plaintext",
                    "refresh_token": "refresh",
                    "expires_in": 3600,
                    "scope": "openid email",
                },
            )
        )
        respx.get("https://openidconnect.googleapis.com/v1/userinfo").mock(
            return_value=httpx.Response(
                200, json={"email": "agent-one@example.com", "email_verified": True}
            )
        )
        result = client.get(
            "/api/v1/integrations/google/callback",
            params={"state": state, "code": "code"},
            follow_redirects=False,
        )
        assert result.status_code == 303, result.text
        assert (
            client.get(
                "/api/v1/integrations/google/callback",
                params={"state": state, "code": "code"},
                follow_redirects=False,
            ).status_code
            == 400
        )
    with factory() as db:
        integration = db.scalar(select(Integration))
        assert "never-plaintext" not in integration.token_ciphertext
        assert db.scalar(select(OAuthState)) is None


def test_gmail_full_incremental_expired_cursor_and_idempotency(
    client, account, factory, configured_google
):
    actor = configured_google
    body = base64.urlsafe_b64encode(b"Our budget is $500,000. Looking for a property.").decode()
    with respx.mock:
        respx.get("https://www.googleapis.com/gmail/v1/users/me/profile").mock(
            return_value=httpx.Response(200, json={"historyId": "200"})
        )
        respx.get("https://www.googleapis.com/gmail/v1/users/me/messages").mock(
            return_value=httpx.Response(200, json={"messages": [{"id": "m1"}]})
        )
        respx.get("https://www.googleapis.com/gmail/v1/users/me/messages/m1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "m1",
                    "threadId": "t1",
                    "internalDate": "1700000000000",
                    "payload": {
                        "mimeType": "text/plain",
                        "headers": [
                            {"name": "From", "value": "A Buyer <buyer@example.com>"},
                            {"name": "To", "value": "agent-one@example.com"},
                            {"name": "Subject", "value": "Property search"},
                        ],
                        "body": {"data": body},
                    },
                },
            )
        )
        history = respx.get("https://www.googleapis.com/gmail/v1/users/me/history").mock(
            return_value=httpx.Response(
                200, json={"history": [{"messagesAdded": [{"message": {"id": "m1"}}]}]}
            )
        )
        with factory() as db:
            db.info["org_id"] = actor.org_id
            assert google.sync_gmail(db, actor) == 1
            db.commit()
            assert google.sync_gmail(db, actor) == 0
            history.mock(return_value=httpx.Response(404))
            assert google.sync_gmail(db, actor) == 0
            db.commit()
            assert len(db.scalars(select(Communication)).all()) == 1
            assert db.scalar(select(SyncCursor)).cursor == "200"


def test_expired_google_token_refresh(configured_google, factory):
    actor = configured_google
    with factory() as db:
        db.info["org_id"] = actor.org_id
        integration = db.scalar(select(Integration))
        integration.token_ciphertext = (
            google.cipher()
            .encrypt(
                json.dumps(
                    {"access_token": "expired", "refresh_token": "refresh", "expires_at": 0}
                ).encode()
            )
            .decode()
        )
        db.commit()
        with respx.mock:
            refresh = respx.post("https://oauth2.googleapis.com/token").mock(
                return_value=httpx.Response(
                    200, json={"access_token": "renewed", "expires_in": 3600}
                )
            )
            client = google.GoogleClient(db, actor)
            assert client.access_token == "renewed"
            assert refresh.called


def test_calendar_invalid_cursor_falls_back(configured_google, factory):
    actor = configured_google
    with factory() as db:
        db.info["org_id"] = actor.org_id
        db.add(
            SyncCursor(
                org_id=actor.org_id,
                user_id=actor.user_id,
                resource="calendar:primary",
                cursor="expired",
            )
        )
        db.commit()
        with respx.mock:
            endpoint = respx.get("https://www.googleapis.com/calendar/v3/calendars/primary/events")
            endpoint.mock(
                side_effect=[
                    httpx.Response(410),
                    httpx.Response(200, json={"items": [], "nextSyncToken": "fresh"}),
                ]
            )
            assert google.sync_calendar(db, actor) == 0
            assert db.scalar(select(SyncCursor)).cursor == "fresh"


def test_google_post_timeout_is_uncertain(configured_google, factory):
    with factory() as db:
        db.info["org_id"] = configured_google.org_id
        client = google.GoogleClient(db, configured_google)
        with respx.mock:
            respx.post("https://www.googleapis.com/gmail/v1/users/me/messages/send").mock(
                side_effect=httpx.ReadTimeout("uncertain")
            )
            with pytest.raises(DomainError) as exc:
                client.request("POST", "gmail/v1/users/me/messages/send", body={"raw": "message"})
            assert exc.value.code == "external_uncertain"


def test_ai_timeout_and_invalid_structured_response(monkeypatch):
    monkeypatch.setattr(settings, "ai_api_key", "test-key")
    with respx.mock:
        route = respx.post("https://api.openai.com/v1/responses").mock(
            side_effect=httpx.ReadTimeout("timeout")
        )
        with pytest.raises(DomainError) as exc:
            OpenAIProvider().structured("Answer", {}, Answer)
        assert exc.value.code == "ai_timeout"
        route.mock(
            return_value=httpx.Response(
                200, json={"output": [{"content": [{"type": "output_text", "text": "not JSON"}]}]}
            )
        )
        with pytest.raises(DomainError) as exc:
            OpenAIProvider().structured("Answer", {}, Answer)
        assert exc.value.code == "ai_invalid_response"


def signature(payload, secret, timestamp=None):
    stamp = int(time.time()) if timestamp is None else timestamp
    mac = hmac.new(
        secret.encode(), str(stamp).encode() + b"." + payload, hashlib.sha256
    ).hexdigest()
    return f"t={stamp},v1={mac}"


def test_stripe_signature_duplicate_and_stale_events(client, account, factory, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "stripe_secret_key", "test-key")
    monkeypatch.setattr(settings, "stripe_webhook_secret", "test-webhook")
    monkeypatch.setattr(settings, "stripe_price_id", "price_test")
    with factory() as db:
        row = db.scalar(select(Subscription))
        row.customer_id = "cus_test"
        db.commit()
    event = {
        "id": "evt_1",
        "type": "customer.subscription.updated",
        "created": 100,
        "data": {"object": {"id": "sub_test", "customer": "cus_test"}},
    }
    payload = json.dumps(event).encode()
    with factory() as db:
        with pytest.raises(DomainError):
            billing.webhook(db, payload, "invalid")
        with pytest.raises(DomainError):
            billing.webhook(db, payload, signature(payload, "test-webhook", 1))
        with respx.mock:
            route = respx.get("https://api.stripe.com/v1/subscriptions/sub_test").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "id": "sub_test",
                        "customer": "cus_test",
                        "status": "active",
                        "items": {"data": [{"price": {"id": "price_test"}}]},
                    },
                )
            )
            assert billing.webhook(db, payload, signature(payload, "test-webhook"))
            db.commit()
            assert not billing.webhook(db, payload, signature(payload, "test-webhook"))
            assert route.call_count == 1
            assert db.scalar(select(Subscription)).status == "active"


def test_worker_crash_recovery_never_resends_external_action(client, contact, account, factory):
    with factory() as db:
        action = AIAction(
            org_id=account["organization"]["id"],
            contact_id=contact["id"],
            kind="send_email",
            title="Email",
            reason="Approved",
            payload={},
            status="executing",
        )
        db.add(action)
        db.flush()
        db.add(
            Job(
                org_id=action.org_id,
                kind="execute_action",
                payload={"action_id": action.id},
                dedupe_key="crash",
                status="running",
                lease_until=now() - timedelta(minutes=1),
            )
        )
        db.commit()
    assert tick()
    with factory() as db:
        assert db.scalar(select(AIAction)).status == "uncertain"
        assert db.scalar(select(Job)).status == "dead"
