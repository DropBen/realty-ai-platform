import json

import pytest
import respx
import test_integrations as integration_fixtures
from cryptography.fernet import Fernet
from pydantic import ValidationError
from realty import billing, google, identity
from realty.config import Settings, settings
from realty.errors import DomainError
from realty.intelligence import Answer, invoke
from realty.jobs import enqueue, tick
from realty.models import Integration, Job, Organization, User
from realty.security import Principal
from sqlalchemy import select

configured_google = integration_fixtures.configured_google


def test_invalid_startup_configuration_does_not_print_secrets():
    with pytest.raises(ValidationError) as failure:
        Settings(
            _env_file=None, app_env="typo", google_client_secret="unique-secret-must-not-appear"
        )
    assert "unique-secret-must-not-appear" not in str(failure.value)


@pytest.mark.parametrize("service", ["oauth", "google", "billing", "ai", "queued_smtp", "smtp"])
def test_demo_tenant_stays_isolated_when_runtime_switches_to_live(
    account, factory, monkeypatch, service
):
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "google_client_id", "test-client")
    monkeypatch.setattr(settings, "google_client_secret", "test-secret")
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "mail_backend", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.test")
    with factory() as db:
        actor = Principal(account["user"]["id"], account["organization"]["id"], "owner")
        db.info["org_id"] = actor.org_id
        assert db.get(Organization, actor.org_id).is_demo
        with respx.mock, pytest.raises(DomainError) as failure:
            if service == "oauth":
                google.authorize(db, actor, "read")
            elif service == "google":
                google.GoogleClient(db, actor)
            elif service == "billing":
                billing.customer(db, actor)
            elif service == "ai":
                invoke(db, actor, "Test", {}, Answer)
            elif service == "queued_smtp":
                identity.queue_mail(db, db.get(User, actor.user_id), "verify", "Never sent")
            else:
                identity.deliver_mail(db, {"user_id": actor.user_id, "mail_id": "missing"})
        assert failure.value.code == "demo_isolated"


def test_demo_workspace_remains_labelled_in_live_runtime(client, account, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", False)
    assert client.get("/api/v1/auth/me").json()["demo_mode"]
    integrations = client.get("/api/v1/integrations").json()
    assert integrations["demo_mode"] and not integrations["google_configured"]


def expire_connection(factory):
    with factory() as db:
        row = db.scalar(select(Integration))
        row.token_ciphertext = (
            google.cipher()
            .encrypt(
                json.dumps(
                    {"access_token": "old", "refresh_token": "revoked", "expires_at": 0}
                ).encode()
            )
            .decode()
        )
        db.commit()


@pytest.mark.parametrize("entry", ["worker", "api"])
def test_revoked_google_refresh_is_visible_and_not_automatically_retried(
    client, factory, configured_google, entry
):
    actor = configured_google
    expire_connection(factory)
    with respx.mock:
        token = respx.post("https://oauth2.googleapis.com/token").respond(
            400, json={"error": "invalid_grant"}
        )
        if entry == "worker":
            with factory() as db:
                db.info["org_id"] = actor.org_id
                enqueue(db, actor.org_id, "gmail_sync", {"user_id": actor.user_id}, "revoked-token")
                db.commit()
            assert tick()
            assert not tick()
        else:
            response = client.post("/api/v1/integrations/google/sync")
            assert response.status_code == 409
        assert token.call_count == 1
    with factory() as db:
        row = db.scalar(select(Integration))
        assert (row.status, row.last_error) == ("reconnect_required", "google_reconnect")
        if entry == "worker":
            assert db.scalar(select(Job)).status == "dead"


def test_stale_google_failure_cannot_disable_new_credentials(factory, configured_google):
    with factory() as db:
        db.info["org_id"] = configured_google.org_id
        row = db.scalar(select(Integration))
        google.remember_connection_failure(db, row)
        db.rollback()
        row.token_ciphertext = google.cipher().encrypt(b'{"access_token":"replacement"}').decode()
        db.commit()
        google.persist_connection_failure(db)
        db.commit()
        assert row.status == "connected" and row.last_error is None


def test_demoted_user_cannot_fetch_live_calendars(client, factory, configured_google):
    from realty.models import Membership

    with factory() as db:
        db.scalar(select(Membership)).role = "viewer"
        db.commit()
    with respx.mock:
        response = client.get("/api/v1/integrations/google/calendars")
        assert response.status_code == 403
