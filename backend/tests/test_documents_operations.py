from datetime import timedelta

import pytest
from conftest import register
from realty.db import now
from realty.errors import DomainError
from realty.jobs import tick
from realty.models import Job, Subscription
from realty.security import rate_limit
from sqlalchemy import select
from sqlalchemy.exc import OperationalError


def test_document_upload_search_download_and_isolation(client, contact):
    result = client.post(
        "/api/v1/documents",
        files={"file": ("notes.txt", b"Budget confirmed at $650,000", "text/plain")},
        data={"contact_id": contact["id"]},
    )
    assert result.status_code == 201, result.text
    doc = result.json()
    assert "storage_key" not in doc
    assert doc["status"] == "extracted"
    assert client.get("/api/v1/documents?q=Budget").json()["total"] == 1
    download = client.get(f"/api/v1/documents/{doc['id']}/download")
    assert download.status_code == 200
    assert "attachment" in download.headers["content-disposition"]
    assert download.content == b"Budget confirmed at $650,000"
    register(client, "two")
    assert client.get("/api/v1/documents").json()["total"] == 0
    assert client.get(f"/api/v1/documents/{doc['id']}/download").status_code == 404
    assert client.delete(f"/api/v1/documents/{doc['id']}").status_code == 404


def test_invalid_files_and_tenant_reference(client, contact):
    assert (
        client.post(
            "/api/v1/documents", files={"file": ("virus.exe", b"MZ", "text/plain")}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/documents", files={"file": ("fake.pdf", b"NOT PDF", "application/pdf")}
        ).status_code
        == 422
    )
    register(client, "two")
    result = client.post(
        "/api/v1/documents",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        data={"contact_id": contact["id"]},
    )
    assert result.status_code == 404


def test_calendar_conflict_and_invalid_interval(client, account):
    start = now() + timedelta(days=1)
    payload = {
        "title": "Client showing",
        "start_at": start.isoformat(),
        "end_at": (start + timedelta(hours=1)).isoformat(),
    }
    assert client.post("/api/v1/crm/appointments", json=payload).status_code == 201
    assert client.post("/api/v1/crm/appointments", json=payload).status_code == 409
    assert (
        client.post(
            "/api/v1/crm/appointments", json={**payload, "end_at": start.isoformat()}
        ).status_code
        == 422
    )


def test_job_retry_backoff_and_dead_letter(client, account, factory, monkeypatch):
    with factory() as db:
        db.add(
            Job(
                org_id=account["organization"]["id"],
                kind="gmail_sync",
                payload={"user_id": account["user"]["id"]},
                dedupe_key="retry",
            )
        )
        db.commit()

    def unavailable(*args):
        raise DomainError("google_unavailable", "Service unavailable", 503)

    monkeypatch.setattr("realty.google.sync_gmail", unavailable)
    assert tick()
    with factory() as db:
        job = db.scalar(select(Job))
        assert job.status == "queued" and job.attempts == 1 and job.available_at > now()
        job.attempts, job.available_at = 4, now() - timedelta(seconds=1)
        db.commit()
    assert tick()
    with factory() as db:
        assert db.scalar(select(Job)).status == "dead"


def test_database_failure_is_generic(client, account, monkeypatch):
    def failure(db):
        raise OperationalError("query", {}, RuntimeError("secret-database-connection"))

    monkeypatch.setattr("realty.api_work.briefing", failure)
    result = client.get("/api/v1/briefing")
    assert result.status_code == 503
    assert "secret-database-connection" not in result.text


def test_fixed_window_rate_limit(factory):
    with factory() as db:
        rate_limit(db, "limited", 2)
        rate_limit(db, "limited", 2)
        with pytest.raises(DomainError) as exc:
            rate_limit(db, "limited", 2)
        assert exc.value.status == 429


def test_export_redacts_credentials_and_account_delete(client, account, contact, factory):
    export = client.get("/api/v1/account/export")
    assert export.status_code == 200
    assert "password_hash" not in export.text and "token_ciphertext" not in export.text
    assert contact["name"] in export.text
    deleted = client.post(
        "/api/v1/account/delete",
        json={
            "organization_name": account["organization"]["name"],
            "password": "secure-password-123!",
        },
    )
    assert deleted.status_code == 200, deleted.text
    assert client.get("/api/v1/auth/me").status_code == 401
    from realty.models import Contact, Organization, User

    with factory() as db:
        assert db.get(Organization, account["organization"]["id"]) is None
        assert db.get(Contact, contact["id"]) is None
        assert db.get(User, account["user"]["id"]) is None


def test_billing_client_cannot_grant_entitlement(client, account, factory):
    assert (
        client.post(
            "/api/v1/billing", json={"plan": "professional", "status": "active"}
        ).status_code
        == 405
    )
    with factory() as db:
        assert db.scalar(select(Subscription)).status == "trialing"
