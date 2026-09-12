import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import httpx
import pytest
from realty import documents
from realty.jobs import enqueue
from realty.main import app
from realty.models import Job
from sqlalchemy import select


def test_manual_and_scheduled_sync_share_active_job_and_allow_later_sync(account, factory):
    org, user = account["organization"]["id"], account["user"]["id"]
    with factory() as db:
        db.info["org_id"] = org
        first = enqueue(db, org, "gmail_sync", {"user_id": user}, "manual")
        repeated = enqueue(db, org, "gmail_sync", {"user_id": user}, "scheduled")
        assert first.id == repeated.id
        first.status = "running"
        db.commit()
        assert enqueue(db, org, "gmail_sync", {"user_id": user}, "another-click").id == first.id
        first.status = "done"
        db.commit()
        later = enqueue(db, org, "gmail_sync", {"user_id": user}, "later")
        assert later.id != first.id
        assert enqueue(db, org, "gmail_sync", {"user_id": user}, "manual").id == first.id
        db.commit()


def test_operator_retry_cannot_conflict_with_an_active_sync(client, account, factory):
    org, user = account["organization"]["id"], account["user"]["id"]
    with factory() as db:
        old = enqueue(db, org, "gmail_sync", {"user_id": user}, "failed-old")
        old.status = "dead"
        db.commit()
        active = enqueue(db, org, "gmail_sync", {"user_id": user}, "current-sync")
        db.commit()
        old_id, active_id = old.id, active.id
    response = client.post(f"/api/v1/jobs/{old_id}/retry")
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "sync_already_active"
    with factory() as db:
        assert db.get(Job, old_id).status == "dead"
        assert db.get(Job, active_id).status == "queued"


def test_distinct_calendar_resources_are_not_accidentally_coalesced(account, factory):
    org, user = account["organization"]["id"], account["user"]["id"]
    with factory() as db:
        jobs = [
            enqueue(db, org, kind, {"user_id": user_id, "calendar_id": calendar}, str(index))
            for index, (kind, user_id, calendar) in enumerate(
                [
                    ("gmail_sync", user, "primary"),
                    ("calendar_sync", user, "primary"),
                    ("calendar_sync", user, "other@example.test"),
                    ("calendar_sync", "another-user", "primary"),
                ]
            )
        ]
        assert len({job.id for job in jobs}) == 4


def test_concurrent_postgres_sync_reservations_coalesce(account, factory):
    with factory() as db:
        if db.get_bind().dialect.name != "postgresql":
            pytest.skip("Requires independent PostgreSQL transactions.")
    barrier = Barrier(2)
    org, user = account["organization"]["id"], account["user"]["id"]

    def reserve(key):
        with factory() as db:
            db.info["org_id"] = org
            barrier.wait(timeout=5)
            job = enqueue(db, org, "gmail_sync", {"user_id": user}, key)
            db.commit()
            return job.id

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert len(set(pool.map(reserve, ["manual", "scheduled"]))) == 1
    with factory() as db:
        assert len(db.scalars(select(Job)).all()) == 1


def test_slow_document_storage_does_not_block_api_liveness(client, account, monkeypatch):
    started, release = Event(), Event()
    original = documents.LocalStorage.put

    def slow_put(self, key, content):
        started.set()
        assert release.wait(timeout=5), "The event loop did not remain responsive."
        original(self, key, content)

    monkeypatch.setattr(documents.LocalStorage, "put", slow_put)

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            cookies=dict(client.cookies),
            headers={"x-csrf-token": account["csrf_token"]},
        ) as http:
            upload = asyncio.create_task(
                http.post(
                    "/api/v1/documents", files={"file": ("responsiveness.txt", b"Test fixture")}
                )
            )
            try:
                assert await asyncio.to_thread(started.wait, 2)
                assert not upload.done()
                response = await asyncio.wait_for(http.get("/health/live"), timeout=1)
                assert response.status_code == 200
                assert not upload.done()
            finally:
                release.set()
                response = await upload
            assert response.status_code == 201, response.text

    asyncio.run(exercise())
