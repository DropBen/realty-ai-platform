from datetime import datetime, timedelta

import httpx
import pytest
import respx
from conftest import register
from realty import documents, google, jobs, operations
from realty.config import settings
from realty.db import now
from realty.documents import DocumentAnalysis, DocumentEntity
from realty.errors import DomainError
from realty.models import Commitment, Document, Job, Notification, StorageDeletion
from realty.security import Principal
from sqlalchemy import select, text
from test_integrations import configured_google  # noqa: F401


def test_commitment_confirmation_source_stale_review_and_reminders(
    client, factory, account, contact
):
    with factory() as db:
        item = Commitment(
            org_id=account["organization"]["id"],
            contact_id=contact["id"],
            title="Call tomorrow",
            quote="I will call tomorrow",
            source_id="fictional-email",
            confidence=0.8,
        )
        db.add(item)
        db.commit()
        identifier = item.id
    payload = {
        "version": 1,
        "title": "Call Jordan",
        "status": "confirmed",
        "due_at": (now() - timedelta(hours=1)).isoformat(),
        "responsible_user": account["user"]["id"],
    }
    assert (
        client.post(
            f"/api/v1/commitments/{identifier}/review", json={**payload, "responsible_user": None}
        ).status_code
        == 422
    )
    result = client.post(f"/api/v1/commitments/{identifier}/review", json=payload)
    assert result.status_code == 200, result.text
    assert result.json()["quote"] == "I will call tomorrow"
    assert client.post(f"/api/v1/commitments/{identifier}/review", json=payload).status_code == 409
    assert len(client.get("/api/v1/briefing").json()["overdue_commitments"]) == 1
    jobs.schedule_recurring()
    jobs.schedule_recurring()
    with factory() as db:
        reminders = list(db.scalars(select(Job).where(Job.kind == "commitment_reminder")))
        assert len(reminders) == 1
        db.info["org_id"] = account["organization"]["id"]
        jobs.dispatch(db, reminders[0])
        db.commit()
        assert db.scalar(select(Notification)).title == "Commitment overdue"
    done = client.post(
        f"/api/v1/commitments/{identifier}/review", json={**payload, "version": 2, "status": "done"}
    )
    assert done.status_code == 200
    register(client, "foreign")
    assert (
        client.post(
            f"/api/v1/commitments/{identifier}/review", json={**payload, "version": 3}
        ).status_code
        == 404
    )


def document_fixture(client):
    response = client.post(
        "/api/v1/documents",
        files={
            "file": (
                "offer.txt",
                b"Buyer: Jordan. Offer amount: $550,000. Closing: 2026-12-15.",
                "text/plain",
            )
        },
    )
    assert response.status_code == 201
    return response.json()


def test_document_analysis_exact_evidence_review_and_no_crm_mutation(
    client, account, factory, monkeypatch
):
    item = document_fixture(client)

    def response(*args):
        return DocumentAnalysis(
            summary="Jordan submitted an offer of $550,000.",
            source_id=item["id"],
            classification="purchase_agreement",
            entities=[
                DocumentEntity(kind="amount", value="$550,000", quote="Offer amount: $550,000.")
            ],
        )

    monkeypatch.setattr("realty.intelligence.invoke", response)
    analyzed = client.post(f"/api/v1/documents/{item['id']}/summarize")
    assert analyzed.status_code == 200, analyzed.text
    assert analyzed.json()["classification"] == "unclassified"
    assert analyzed.json()["analysis"]["state"] == "extracted"
    assert client.get("/api/v1/crm/contacts").json()["total"] == 0
    reviewed = client.post(
        f"/api/v1/documents/{item['id']}/review",
        json={"classification": "purchase_agreement", "source_hash": item["sha256"]},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["reviewed_by"] == account["user"]["id"]
    assert reviewed.json()["classification"] == "purchase_agreement"
    register(client, "document-foreign")
    assert client.post(f"/api/v1/documents/{item['id']}/summarize").status_code == 404


@pytest.mark.parametrize(
    "source,quote,value",
    [
        ("foreign-id", "Offer amount: $550,000.", "$550,000"),
        (None, "Invented quote", "Invented"),
        (None, "Offer amount: $550,000.", "$700,000"),
    ],
)
def test_document_analysis_rejects_fabricated_evidence(
    client, account, monkeypatch, source, quote, value
):
    item = document_fixture(client)
    monkeypatch.setattr(
        "realty.intelligence.invoke",
        lambda *args: DocumentAnalysis(
            summary="Untrusted output",
            source_id=source or item["id"],
            classification="other",
            entities=[DocumentEntity(kind="amount", value=value, quote=quote)],
        ),
    )
    response = client.post(f"/api/v1/documents/{item['id']}/summarize")
    assert response.status_code == 422
    assert client.get("/api/v1/documents").json()["items"][0]["summary"] is None


def test_document_storage_survives_failed_delete_and_is_purged_after_commit(
    client, account, factory
):
    item = document_fixture(client)
    with factory() as db:
        db.info["org_id"] = account["organization"]["id"]
        document = db.get(Document, item["id"])
        key = document.storage_key
        documents.queue_deletion(db, document)
        db.delete(document)
        db.rollback()
        assert documents.storage().get(key)
        assert db.scalar(select(StorageDeletion)) is None
    assert client.delete(f"/api/v1/documents/{item['id']}").status_code == 200
    operations.maintenance(factory)
    with factory() as db:
        assert db.scalar(select(StorageDeletion)) is None
    assert not documents.LocalStorage().path(key).exists()


def test_upload_blob_is_removed_on_transaction_rollback(factory, account):
    with factory() as db:
        db.info["org_id"] = account["organization"]["id"]
        document = documents.upload(
            db,
            Principal(account["user"]["id"], account["organization"]["id"], "owner"),
            "rollback.txt",
            b"Rollback this upload",
            None,
        )
        key = document.storage_key
        db.rollback()
        assert not documents.LocalStorage().path(key).exists()


@pytest.mark.parametrize(
    "value,zone,expected",
    [
        ({"date": "2026-03-08"}, "America/New_York", datetime(2026, 3, 8, 5)),
        ({"date": "2026-03-09"}, "America/New_York", datetime(2026, 3, 9, 4)),
        (
            {"dateTime": "2026-11-01T01:30:00-04:00"},
            "America/New_York",
            datetime(2026, 11, 1, 5, 30),
        ),
        (
            {"dateTime": "2026-11-01T01:30:00-05:00"},
            "America/New_York",
            datetime(2026, 11, 1, 6, 30),
        ),
    ],
)
def test_calendar_timezone_and_dst(value, zone, expected):
    assert google.calendar_time(value, zone) == expected


@pytest.mark.parametrize(
    "value",
    [
        {"dateTime": "2026-03-08T02:30:00"},
        {"dateTime": "2026-11-01T01:30:00"},
        {"date": "2026-02-30"},
        {"date": "2026-01-01", "timeZone": "invalid/zone"},
    ],
)
def test_calendar_rejects_ambiguous_missing_and_invalid_times(value):
    with pytest.raises(DomainError):
        google.calendar_time(value, "America/New_York")


@pytest.fixture
def google_actor(request):
    return request.getfixturevalue("configured_google")


def test_calendar_all_day_dst_and_recurrence_metadata(google_actor, factory):
    from realty.models import Appointment

    actor = google_actor
    with factory() as db, respx.mock:
        db.info["org_id"] = actor.org_id
        respx.get("https://www.googleapis.com/calendar/v3/calendars/primary/events").mock(
            return_value=httpx.Response(
                200,
                json={
                    "timeZone": "America/New_York",
                    "nextSyncToken": "done",
                    "items": [
                        {
                            "id": "event1",
                            "summary": "All-day showing",
                            "start": {"date": "2026-03-08"},
                            "end": {"date": "2026-03-09"},
                            "recurringEventId": "series1",
                            "originalStartTime": {"date": "2026-03-08"},
                        }
                    ],
                },
            )
        )
        assert google.sync_calendar(db, actor) == 1
        db.commit()
        event = db.scalar(select(Appointment))
        assert event.all_day and event.timezone == "America/New_York"
        assert event.end_at - event.start_at == timedelta(hours=23)
        assert event.recurrence_id == "series1"
        assert event.original_start == "2026-03-08"


def listing_batch():
    return {
        "provider": "test_feed",
        "items": [
            {
                "reference": "listing1",
                "updated_at": "2026-01-01T00:00:00Z",
                "property": {
                    "address": "12 Test Lane",
                    "location": "Example City",
                    "price": 500000,
                    "bedrooms": 3,
                    "bathrooms": 2,
                },
            }
        ],
    }


def test_listing_import_preview_idempotency_stale_and_manual_conflict(client, account):
    batch = listing_batch()
    preview = client.post("/api/v1/listings/preview", json=batch)
    assert preview.status_code == 200, preview.text
    assert preview.json()["items"][0]["status"] == "create"
    assert client.get("/api/v1/crm/properties").json()["total"] == 0
    imported = client.post("/api/v1/listings/import", json=batch)
    assert imported.status_code == 200, imported.text
    assert (
        client.post("/api/v1/listings/import", json=batch).json()["items"][0]["status"]
        == "unchanged"
    )
    batch["items"][0]["updated_at"] = "2025-12-31T00:00:00Z"
    assert (
        client.post("/api/v1/listings/import", json=batch).json()["items"][0]["status"] == "stale"
    )
    prop = imported.json()["items"][0]["property"]
    manual = {
        **batch["items"][0]["property"],
        "price": 520000,
        "source": "test_feed",
        "listing_reference": "listing1",
    }
    assert client.put(f"/api/v1/crm/properties/{prop['id']}", json=manual).status_code == 200
    batch["items"][0]["updated_at"] = "2026-01-02T00:00:00Z"
    batch["items"][0]["property"]["price"] = 510000
    assert client.post("/api/v1/listings/import", json=batch).status_code == 409
    register(client, "listing-foreign")
    assert client.get("/api/v1/crm/properties").json()["total"] == 0
    assert (
        client.post("/api/v1/listings/preview", json=batch).json()["items"][0]["status"] == "create"
    )


def test_csv_preview_parses_quoted_fields_and_rejects_bad_records(client, account):
    csv = b'reference,updated_at,address,location,price,bedrooms,bathrooms,features\nabc,2026-01-01T00:00:00Z,"12 Main, Unit 2",Example,500000,3,2,garage;garden\n'
    response = client.post(
        "/api/v1/listings/preview-file", files={"file": ("properties.csv", csv, "text/csv")}
    )
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["address"] == "12 Main, Unit 2"
    assert client.post("/api/v1/listings/import", json=response.json()["batch"]).status_code == 200
    assert (
        client.post(
            "/api/v1/listings/preview-file",
            files={"file": ("invalid.csv", b"malformed\nrecord", "text/csv")},
        ).status_code
        == 422
    )


def test_operations_metrics_auth_schema_and_tenant_scope(client, account, factory, monkeypatch):
    monkeypatch.setattr(settings, "metrics_token", "operator-test-token")
    assert client.get("/internal/metrics").status_code == 403
    assert (
        client.get(
            "/internal/metrics", headers={"Authorization": "Bearer operator-test-token"}
        ).status_code
        == 200
    )
    operations.pulse(factory)
    assert client.get("/api/v1/operations").json()["worker_available"]
    with factory() as db:
        jobs.enqueue(db, account["organization"]["id"], "test", {}, "ops-isolation")
        db.commit()
    register(client, "operations-foreign")
    assert client.get("/api/v1/operations").json()["jobs"] == {}
    with factory() as db:
        db.execute(text("UPDATE alembic_version SET version_num='old-revision'"))
        db.commit()
    assert client.get("/health/ready").status_code == 503
    assert client.get("/health/live").status_code == 200
