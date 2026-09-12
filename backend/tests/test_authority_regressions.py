"""Regression cases from the autonomous audit; provider traffic is always intercepted."""

from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx
from cryptography.fernet import Fernet
from pydantic import ValidationError
from realty.config import Settings, settings
from realty.db import now
from realty.jobs import tick
from realty.models import AIAction, Integration, Job, Membership, Organization
from sqlalchemy import select
from test_actions import decision, propose


@pytest.mark.parametrize("value", [123, True, [], {}, ["2026-09-11"]])
def test_malformed_dates_return_validation_errors(client, account, value):
    response = client.post("/api/v1/crm/tasks", json={"title": "Follow up", "due_at": value})
    assert response.status_code == 422, response.text
    assert client.get("/api/v1/crm/tasks").json()["total"] == 0


@pytest.mark.parametrize(
    "values",
    [
        {"app_env": "prodution"},
        {"app_env": "staging", "demo_mode": True},
        {"storage_backend": "azuer"},
        {"ai_provider": "opneai", "demo_mode": False},
        {"session_hours": 0},
        {"ai_timeout_seconds": -1},
        {"ai_monthly_limit": -1},
        {"smtp_port": 70000},
        {"app_origin": "https://app.example.com/path"},
        {"api_origin": "https://user:password@app.example.com"},
    ],
)
def test_invalid_configuration_fails_closed(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


@pytest.fixture
def oauth_start(client, account, monkeypatch, live_account):
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "google_client_id", "test-client")
    monkeypatch.setattr(settings, "google_client_secret", "test-secret")
    response = client.post("/api/v1/integrations/google/authorize")
    assert response.status_code == 200
    return parse_qs(urlsplit(response.json()["url"]).query)["state"][0]


def oauth_routes(router=respx):
    token = router.post("https://oauth2.googleapis.com/token").respond(
        200,
        json={"access_token": "test-access", "refresh_token": "test-refresh", "expires_in": 3600},
    )
    router.get("https://openidconnect.googleapis.com/v1/userinfo").respond(
        200, json={"email": "agent-one@example.com", "email_verified": True}
    )
    return token


@pytest.mark.parametrize("change", ["switch", "demote"])
def test_oauth_rejects_changed_workspace_or_permission(
    client, account, factory, oauth_start, change
):
    with factory() as db:
        if change == "switch":
            org = Organization(name="Second workspace")
            db.add(org)
            db.flush()
            db.add(Membership(org_id=org.id, user_id=account["user"]["id"], role="owner"))
            target = org.id
        else:
            db.scalar(select(Membership)).role = "viewer"
        db.commit()
    if change == "switch":
        assert client.post(f"/api/v1/account/organizations/{target}/switch").status_code == 200
    with respx.mock(assert_all_called=False) as router:
        token = oauth_routes(router)
        response = client.get(
            "/api/v1/integrations/google/callback",
            params={"state": oauth_start, "code": "code"},
            follow_redirects=False,
        )
        assert response.status_code == (400 if change == "switch" else 403), response.text
        assert not token.called
    with factory() as db:
        assert db.scalar(select(Integration)) is None


def test_oauth_rechecks_permission_after_provider_response(client, factory, oauth_start):
    with respx.mock:
        token = oauth_routes()

        def demote(_request):
            with factory() as db:
                db.scalar(select(Membership)).role = "viewer"
                db.commit()
            return httpx.Response(200, json={"access_token": "test-access", "expires_in": 3600})

        token.mock(side_effect=demote)
        response = client.get(
            "/api/v1/integrations/google/callback",
            params={"state": oauth_start, "code": "code"},
            follow_redirects=False,
        )
        assert response.status_code == 403, response.text
    with factory() as db:
        assert db.scalar(select(Integration)) is None


def test_manual_edit_after_approval_is_not_overwritten(client, contact, factory):
    action = propose(client, contact)
    assert decision(client, action, "approve").status_code == 200
    assert (
        client.put(
            f"/api/v1/contacts/{contact['id']}/preferences", json={"budget_max": 900000}
        ).status_code
        == 200
    )
    assert tick()
    with factory() as db:
        row = db.scalar(select(AIAction))
        assert (row.status, row.error_code) == ("failed", "changed_since_approval")
    profile = client.get(f"/api/v1/contacts/{contact['id']}/profile").json()
    assert profile["preferences"]["budget_max"] == 900000


def test_undo_cannot_restore_an_invalid_budget_range(client, contact, factory):
    path = f"/api/v1/contacts/{contact['id']}/preferences"
    assert client.put(path, json={"budget_max": 500000}).status_code == 200
    action = propose(client, contact)
    decision(client, action, "approve")
    assert tick()
    assert client.put(path, json={"budget_min": 600000, "budget_max": 650000}).status_code == 200
    with factory() as db:
        action["version"] = db.scalar(select(AIAction)).version
    response = decision(client, action, "undo")
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "changed_since_action"


@pytest.mark.parametrize("reason", ["expired_action", "forbidden"])
def test_invalidated_approval_reaches_terminal_reviewable_state(client, contact, factory, reason):
    action = propose(client, contact)
    decision(client, action, "approve")
    with factory() as db:
        if reason == "expired_action":
            db.scalar(select(AIAction)).expires_at = now() - timedelta(seconds=1)
        else:
            db.scalar(select(Membership)).role = "viewer"
        db.commit()
    assert tick()
    with factory() as db:
        row = db.scalar(select(AIAction))
        assert (row.status, row.error_code) == ("failed", reason)
        assert db.scalar(select(Job)).status == "dead"
    assert not tick()


@pytest.mark.parametrize(
    "payload", [{}, [], {"access_token": 123}, {"access_token": "x", "expires_in": -1}]
)
def test_malformed_oauth_token_is_a_safe_provider_error(client, factory, oauth_start, payload):
    with respx.mock(assert_all_called=False) as router:
        token = oauth_routes(router)
        token.respond(200, json=payload)
        response = client.get(
            "/api/v1/integrations/google/callback",
            params={"state": oauth_start, "code": "code"},
            follow_redirects=False,
        )
        assert response.status_code == 502, response.text
        assert response.json()["error"]["code"] == "google_auth_failed"
    with factory() as db:
        assert db.scalar(select(Integration)) is None


@pytest.mark.parametrize(
    "profile",
    [
        [],
        {},
        {"email": "bad", "email_verified": True},
        {"email": "agent@example.com", "email_verified": "false"},
    ],
)
def test_malformed_google_identity_is_rejected(client, factory, oauth_start, profile):
    with respx.mock:
        oauth_routes()
        respx.get("https://openidconnect.googleapis.com/v1/userinfo").respond(200, json=profile)
        response = client.get(
            "/api/v1/integrations/google/callback",
            params={"state": oauth_start, "code": "code"},
            follow_redirects=False,
        )
        assert response.status_code == 502, response.text
        assert response.json()["error"]["code"] == "google_identity"
    with factory() as db:
        assert db.scalar(select(Integration)) is None


def test_concurrent_manual_preference_write_wins_over_stale_approval(
    client, contact, account, factory
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from realty.models import Preference
    from realty.repository import locked_preference
    from sqlalchemy import event

    with factory() as db:
        if db.get_bind().dialect.name != "postgresql":
            pytest.skip("Cross-connection row-lock test requires PostgreSQL")
    action = propose(client, contact)
    assert decision(client, action, "approve").status_code == 200
    with factory() as manual:
        manual.info["org_id"] = account["organization"]["id"]
        assert locked_preference(manual, contact["id"]) is None
        manual.add(
            Preference(org_id=manual.info["org_id"], contact_id=contact["id"], budget_max=900000)
        )
        manual.flush()
        waiting = Event()

        def attempted(_conn, _cursor, statement, _params, _context, _many):
            if statement.startswith("UPDATE contacts"):
                waiting.set()

        engine = manual.get_bind()
        event.listen(engine, "before_cursor_execute", attempted)
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(tick)
                try:
                    assert waiting.wait(5), "Worker did not reach the preference lock"
                    assert not future.done(), "The worker bypassed the writer's lock"
                finally:
                    manual.commit()
                assert future.result(timeout=10)
        finally:
            event.remove(engine, "before_cursor_execute", attempted)
    with factory() as db:
        assert db.scalar(select(Preference)).budget_max == 900000
        assert db.scalar(select(AIAction)).error_code == "changed_since_approval"
