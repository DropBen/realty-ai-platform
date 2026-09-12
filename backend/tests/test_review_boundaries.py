"""Real API/database regressions for the review and extraction boundaries."""

from datetime import timedelta

import pytest
from realty import intelligence
from realty.actions import execute
from realty.db import now
from realty.errors import DomainError
from realty.jobs import tick
from realty.models import (
    Activity,
    AIAction,
    Appointment,
    Commitment,
    Communication,
    Fact,
    Task,
    Usage,
)
from sqlalchemy import select
from test_actions import decision, propose


def test_withdraw_scheduled_approval_and_ignore_its_old_job(client, contact, factory):
    action = propose(
        client, contact, "create_task", {"title": "Call buyer", "contact_id": contact["id"]}
    )
    approved = decision(
        client, action, "approve", scheduled_at=(now() + timedelta(hours=1)).isoformat()
    ).json()
    withdrawn = decision(client, approved, "reject")
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["status"] == "rejected"
    from realty.models import Job

    with factory() as db:
        db.scalar(select(Job)).available_at = now()
        db.commit()
    assert tick()
    with factory() as db:
        assert db.scalar(select(Task)) is None
        assert db.scalar(select(Job)).status == "done"
        row = db.scalar(select(AIAction))
        assert row.approved_hash is None and row.approved_by is None


def test_editing_queued_action_requires_fresh_approval(client, contact, factory):
    action = propose(client, contact)
    approved = decision(client, action, "approve").json()
    edited = decision(
        client,
        approved,
        "edit",
        payload={"contact_id": contact["id"], "changes": {"budget_max": 700000}},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["status"] == "pending"
    assert tick()  # old job is harmless
    with factory() as db:
        assert db.scalar(select(Fact)) is None
    assert decision(client, edited.json(), "approve").status_code == 200
    assert tick()
    assert (
        client.get(f"/api/v1/contacts/{contact['id']}/profile").json()["preferences"]["budget_max"]
        == 700000
    )


def test_cannot_withdraw_an_action_after_execution_started(client, contact, factory):
    action = propose(client, contact)
    approved = decision(client, action, "approve").json()
    with factory() as db:
        db.scalar(select(AIAction)).status = "executing"
        db.commit()
    assert decision(client, approved, "reject").status_code == 409


def test_payload_contact_is_used_for_action_and_timeline(client, contact, factory):
    response = client.post(
        "/api/v1/actions",
        json={
            "kind": "create_task",
            "title": "Call buyer",
            "reason": "Requested a call",
            "payload": {"title": "Call buyer", "contact_id": contact["id"]},
        },
    )
    assert response.status_code == 201, response.text
    action = response.json()
    assert action["contact_id"] == contact["id"]
    assert decision(client, action, "approve").status_code == 200
    assert tick()
    with factory() as db:
        assert (
            db.scalar(select(Activity).where(Activity.source_id == action["id"])).contact_id
            == contact["id"]
        )


@pytest.mark.parametrize("kind", ["calendar_update", "calendar_delete"])
def test_calendar_action_cannot_reference_a_different_contact(
    client, contact, account, factory, kind
):
    other = client.post("/api/v1/crm/contacts", json={"name": "Other buyer"}).json()
    with factory() as db:
        appointment = Appointment(
            org_id=account["organization"]["id"],
            contact_id=other["id"],
            title="Other showing",
            start_at=now(),
            end_at=now() + timedelta(hours=1),
        )
        db.add(appointment)
        db.commit()
        appointment_id = appointment.id
    payload = {"appointment_id": appointment_id}
    if kind == "calendar_update":
        payload["event"] = {
            "title": "Changed showing",
            "start_at": now().isoformat(),
            "end_at": (now() + timedelta(hours=1)).isoformat(),
            "contact_id": contact["id"],
        }
    response = client.post(
        "/api/v1/actions",
        json={
            "kind": kind,
            "title": "Change event",
            "reason": "Review",
            "contact_id": contact["id"],
            "payload": payload,
        },
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "contact_mismatch"


def message_fixture(factory, account, contact):
    with factory() as db:
        message = Communication(
            org_id=account["organization"]["id"],
            contact_id=contact["id"],
            sender=contact["email"],
            recipient=account["user"]["email"],
            subject="Our search",
            body="Our budget is $650,000. I'll send the approval tomorrow.",
        )
        db.add(message)
        db.commit()
        return message.id


def test_overlapping_analysis_records_facts_commitments_and_usage_once(
    client, account, contact, factory, monkeypatch
):
    message_id = message_fixture(factory, account, contact)
    original = intelligence.extract_demo
    entered = False

    def overlapping(body):
        nonlocal entered
        if not entered:
            entered = True
            # Another request finishes while this request is waiting for extraction.
            assert client.post(f"/api/v1/inbox/{message_id}/analyze").status_code == 200
        return original(body)

    monkeypatch.setattr(intelligence, "extract_demo", overlapping)
    assert client.post(f"/api/v1/inbox/{message_id}/analyze").status_code == 200
    with factory() as db:
        assert len(db.scalars(select(Fact)).all()) == 1
        assert len(db.scalars(select(Commitment)).all()) == 1
        assert len(db.scalars(select(Usage).where(Usage.metric == "emails_processed")).all()) == 1
        assert len(db.scalars(select(AIAction)).all()) == 2


def test_source_changed_during_extraction_cannot_create_stale_facts(
    client, account, contact, factory, monkeypatch
):
    message_id = message_fixture(factory, account, contact)
    original = intelligence.extract_demo

    def changed(body):
        with factory() as db:
            db.get(Communication, message_id).body = "No budget confirmed."
            db.commit()
        return original(body)

    monkeypatch.setattr(intelligence, "extract_demo", changed)
    response = client.post(f"/api/v1/inbox/{message_id}/analyze")
    assert response.status_code == 409, response.text
    with factory() as db:
        assert db.scalar(select(Fact)) is None
        assert not db.get(Communication, message_id).analyzed


def test_executor_cannot_claim_a_different_approval_revision(
    client, contact, account, factory, monkeypatch
):
    import realty.actions as actions

    action = propose(client, contact)
    decision(client, action, "approve")
    original = actions.checked_payload

    def replace_revision(db, *args):
        value = original(db, *args)
        with factory() as concurrent:
            row = concurrent.get(AIAction, action["id"])
            row.version += 1
            concurrent.commit()
        return value

    monkeypatch.setattr(actions, "checked_payload", replace_revision)
    with factory() as db:
        db.info["org_id"] = account["organization"]["id"]
        with pytest.raises(DomainError, match="changed|worker"):
            execute(db, action["id"])
        db.rollback()
    with factory() as db:
        assert db.scalar(select(Fact)) is None


def test_stale_commitment_session_cannot_overwrite_a_new_review(client, account, contact, factory):
    from realty.commitments import Review, review
    from realty.security import Principal

    with factory() as db:
        item = Commitment(
            org_id=account["organization"]["id"],
            contact_id=contact["id"],
            title="Client promise",
            quote="I'll call tomorrow",
            source_id="email",
            confidence=0.8,
            status="proposed",
        )
        db.add(item)
        db.commit()
        item_id = item.id
    with factory() as stale:
        stale.info["org_id"] = account["organization"]["id"]
        cached = stale.get(Commitment, item_id)
        response = client.post(
            f"/api/v1/commitments/{item_id}/review",
            json={"version": 1, "title": "Rejected promise", "status": "rejected"},
        )
        assert response.status_code == 200, response.text
        assert cached.version == 1
        with pytest.raises(DomainError) as error:
            review(
                item_id,
                Review(version=1, title="Stale edit", status="rejected"),
                Principal(account["user"]["id"], account["organization"]["id"], "owner"),
                stale,
            )
        assert error.value.code == "stale_commitment"
        stale.rollback()
    with factory() as db:
        assert db.get(Commitment, item_id).title == "Rejected promise"


def test_conflicting_duplicate_ai_fields_roll_back_the_whole_extraction(
    client, account, contact, factory, monkeypatch
):
    message_id = message_fixture(factory, account, contact)
    monkeypatch.setattr(
        intelligence,
        "extract_demo",
        lambda _body: intelligence.Extraction(
            summary="Duplicate output",
            commitments=[],
            facts=[
                {
                    "field": "budget_max",
                    "value": 650000,
                    "quote": "budget is $650,000",
                    "confidence": 0.8,
                },
                {"field": "budget_max", "value": 650000, "quote": "$650,000", "confidence": 0.9},
            ],
        ),
    )
    response = client.post(f"/api/v1/inbox/{message_id}/analyze")
    assert response.status_code == 422, response.text
    with factory() as db:
        assert not db.get(Communication, message_id).analyzed
        assert db.scalar(select(Fact)) is None
        assert db.scalar(select(AIAction)) is None
