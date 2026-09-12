import asyncio
import json
from datetime import timedelta
from threading import Event

import httpx
import pytest
import respx
from conftest import register
from realty import billing, jobs
from realty.config import settings
from realty.db import now
from realty.errors import DomainError
from realty.http_security import MAX_REQUEST, SecurityMiddleware
from realty.intelligence import Answer, OpenAIProvider
from realty.leases import Lease, renew_lease
from realty.main import app
from realty.models import Contact, Job, Membership, Subscription, WebhookEvent
from realty.security import principal, rate_limit
from sqlalchemy import select, update
from test_integrations import signature


def test_every_api_route_has_an_explicit_authentication_policy():
    from fastapi.routing import iter_route_contexts

    public = {
        "/api/v1/config",
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/password/request",
        "/api/v1/auth/password/reset",
        "/api/v1/auth/email/verify",
        "/api/v1/auth/mfa/verify",
        "/api/v1/webhooks/stripe",
    }

    def dependencies(dependant):
        return {dependant.call} | {
            call for child in dependant.dependencies for call in dependencies(child)
        }

    checked = []
    for route in iter_route_contexts(app.routes):
        if route.path and route.path.startswith("/api/v1/"):
            assert route.path in public or principal in dependencies(route.dependant), route.path
            checked.append(route.path)
    assert len(checked) >= 60


def test_org_switch_identity_lookup_commits_and_cannot_switch_to_stranger(client, factory, account):
    second = register(client, "second")
    assert (
        client.post(
            f"/api/v1/account/organizations/{account['organization']['id']}/switch"
        ).status_code
        == 403
    )
    with factory() as db:
        db.add(
            Membership(
                org_id=account["organization"]["id"], user_id=second["user"]["id"], role="viewer"
            )
        )
        db.commit()
    assert len(client.get("/api/v1/account/organizations").json()["items"]) == 2
    assert (
        client.post(
            f"/api/v1/account/organizations/{account['organization']['id']}/switch"
        ).status_code
        == 200
    )
    me = client.get("/api/v1/auth/me").json()
    assert me["organization"]["id"] == account["organization"]["id"]
    assert me["role"] == "viewer"
    assert client.post("/api/v1/crm/contacts", json={"name": "Denied"}).status_code == 403


def test_chunked_body_limit_rejects_before_application_runs():
    called, sent = [], []

    async def endpoint(scope, receive, send):
        called.append(True)

    async def run():
        parts = iter(
            [
                {"type": "http.request", "body": b"x" * (MAX_REQUEST // 2), "more_body": True},
                {"type": "http.request", "body": b"x" * (MAX_REQUEST // 2 + 1)},
            ]
        )

        async def receive():
            return next(parts)

        async def send(message):
            sent.append(message)

        await SecurityMiddleware(endpoint)(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/crm/contacts",
                "headers": [],
                "query_string": b"",
            },
            receive,
            send,
        )

    asyncio.run(run())
    assert not called
    assert sent[0]["status"] == 413
    assert dict(sent[0]["headers"])[b"x-content-type-options"] == b"nosniff"
    assert b"payload_too_large" in sent[1]["body"]


def test_rejected_origin_and_length_keep_security_headers(client):
    for headers in [{"origin": "https://attacker.example"}, {"content-length": "-5"}]:
        response = client.post("/api/v1/auth/login", headers=headers, json={})
        assert response.status_code in {400, 403}
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-request-id"]


def test_rate_limit_retry_after(factory):
    with factory() as db:
        rate_limit(db, "test", 1, 60)
        db.commit()
        with pytest.raises(DomainError) as failure:
            rate_limit(db, "test", 1, 60)
        assert 1 <= failure.value.retry_after <= 60


@pytest.mark.parametrize("tokens", [-1, 1.5, "100", True, 1_000_001])
def test_ai_rejects_invalid_metering(monkeypatch, tokens):
    monkeypatch.setattr(settings, "ai_api_key", "test-key")
    with respx.mock:
        respx.post("https://api.openai.com/v1/responses").mock(
            return_value=httpx.Response(
                200,
                json={
                    "output": [
                        {
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps({"answer": "Unknown", "source_ids": []}),
                                }
                            ]
                        }
                    ],
                    "usage": {"total_tokens": tokens},
                },
            )
        )
        with pytest.raises(DomainError, match="validated"):
            OpenAIProvider().structured("answer", {}, Answer)


def test_stripe_canonical_customer_mismatch_rolls_back_receipt(
    account, factory, monkeypatch, live_account
):
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "stripe_webhook_secret", "test-webhook")
    monkeypatch.setattr(
        billing,
        "stripe_request",
        lambda *args: {"id": "sub_test", "customer": "cus_foreign", "status": "active"},
    )
    with factory() as db:
        subscription = db.scalar(select(Subscription))
        subscription.customer_id = "cus_local"
        db.commit()
        body = json.dumps(
            {
                "id": "evt_wrong",
                "type": "customer.subscription.updated",
                "created": 100,
                "data": {"object": {"id": "sub_test", "customer": "cus_local"}},
            }
        ).encode()
        with pytest.raises(DomainError) as failure:
            billing.webhook(db, body, signature(body, "test-webhook"))
        assert failure.value.code == "billing_identity_mismatch"
        db.rollback()
        assert db.scalar(select(Subscription)).status == "trialing"
        assert db.get(WebhookEvent, "evt_wrong") is None


def running_job(factory, org_id):
    with factory() as db:
        job = Job(
            org_id=org_id,
            kind="workflow_event",
            payload={},
            dedupe_key="lease-test",
            status="running",
            attempts=1,
            lease_until=now() + timedelta(seconds=30),
        )
        db.add(job)
        db.commit()
        return job.id


def test_lease_renewal_is_bound_to_attempt_and_expiry(factory, account):
    org = account["organization"]["id"]
    job_id = running_job(factory, org)
    assert renew_lease(factory, job_id, org, 1)
    assert not renew_lease(factory, job_id, org, 0)
    assert not renew_lease(factory, job_id, "other", 1)
    with factory() as db:
        db.execute(update(Job).values(lease_until=now() - timedelta(seconds=1)))
        db.commit()
    assert not renew_lease(factory, job_id, org, 1)


def test_stale_worker_cannot_commit_business_changes(factory, account):
    org = account["organization"]["id"]
    job_id = running_job(factory, org)
    with factory() as db:
        job = db.get(Job, job_id)
        with pytest.raises(DomainError, match="owns"):
            with Lease(db, factory, job):
                with factory() as replacement:
                    replacement.execute(update(Job).where(Job.id == job_id).values(attempts=2))
                    replacement.commit()
                db.add(Contact(org_id=org, name="Stale mutation"))
                db.commit()
        db.rollback()
        assert db.scalar(select(Contact)) is None
        assert db.get(Job, job_id).attempts == 2


def test_postgres_long_worker_renews_during_dispatch(factory, account, monkeypatch):
    if factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("PostgreSQL renewal; SQLite has one development worker")
    import realty.leases as leases

    renewed = Event()
    original = leases.renew_lease

    def observed(*args):
        result = original(*args)
        if result:
            renewed.set()
        return result

    monkeypatch.setattr(leases, "RENEW_SECONDS", 0.02)
    monkeypatch.setattr(leases, "renew_lease", observed)

    def dispatch(db, job):
        assert renewed.wait(3), "Worker did not renew while dispatch was active"

    monkeypatch.setattr(jobs, "dispatch", dispatch)
    with factory() as db:
        jobs.enqueue(db, account["organization"]["id"], "workflow_event", {}, "heartbeat")
        db.commit()
    assert jobs.tick()
    with factory() as db:
        assert db.scalar(select(Job)).status == "done"
