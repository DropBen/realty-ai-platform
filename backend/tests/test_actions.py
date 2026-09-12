from datetime import timedelta

import pytest
from realty.actions import execute
from realty.db import now
from realty.errors import DomainError
from realty.jobs import tick
from realty.models import Activity, AIAction, Audit, Membership, Preference, Task
from sqlalchemy import select


def propose(client, contact, kind="crm_update", payload=None):
    response = client.post(
        "/api/v1/actions",
        json={
            "kind": kind,
            "title": "Review budget",
            "reason": "Buyer explicitly stated a budget.",
            "contact_id": contact["id"],
            "payload": payload or {"contact_id": contact["id"], "changes": {"budget_max": 650000}},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def decision(client, action, choice, **extra):
    return client.post(
        f"/api/v1/actions/{action['id']}/decision",
        json={"decision": choice, "version": action["version"], **extra},
    )


def test_approval_execution_audit_and_undo(client, contact, account, factory):
    action = propose(client, contact)
    assert decision(client, action, "approve").status_code == 200
    assert tick()
    with factory() as db:
        db.info["org_id"] = account["organization"]["id"]
        result = db.scalar(select(AIAction).where(AIAction.id == action["id"]))
        assert result.status == "succeeded"
        assert db.scalar(select(Preference)).budget_max == 650000
        assert db.scalar(select(Audit).where(Audit.action == "action.executed"))
        assert db.scalar(select(Activity).where(Activity.kind == "ai_action"))
        version = result.version
    undone = decision(client, {**action, "version": version}, "undo")
    assert undone.status_code == 200, undone.text
    assert undone.json()["status"] == "undone"
    assert (
        client.get(f"/api/v1/contacts/{contact['id']}/profile").json()["preferences"]["budget_max"]
        is None
    )


def test_cannot_execute_without_approval(client, contact, account, factory):
    action = propose(client, contact)
    with factory() as db:
        db.info["org_id"] = account["organization"]["id"]
        with pytest.raises(DomainError, match="valid approval"):
            execute(db, action["id"])


def test_approval_rechecks_preferences_changed_after_proposal(client, contact):
    action = propose(client, contact)
    assert (
        client.put(
            f"/api/v1/contacts/{contact['id']}/preferences",
            json={"budget_min": 700000},
        ).status_code
        == 200
    )
    response = decision(client, action, "approve")
    assert response.status_code == 422
    assert "existing preferences" in response.text


def test_duplicate_approval_and_job_do_not_duplicate_task(client, contact, account, factory):
    action = propose(
        client, contact, "create_task", {"title": "Call Jordan", "contact_id": contact["id"]}
    )
    assert decision(client, action, "approve").status_code == 200
    assert decision(client, action, "approve").status_code == 409
    assert tick()
    with factory() as db:
        db.info["org_id"] = account["organization"]["id"]
        execute(db, action["id"])
        db.commit()
        assert len(db.scalars(select(Task)).all()) == 1


def test_approved_payload_tampering_and_role_revocation(client, contact, account, factory):
    action = propose(client, contact)
    decision(client, action, "approve")
    with factory() as db:
        db.info["org_id"] = account["organization"]["id"]
        row = db.scalar(select(AIAction))
        row.payload = {"contact_id": contact["id"], "changes": {"budget_max": 999999}}
        db.commit()
        with pytest.raises(DomainError, match="valid approval"):
            execute(db, action["id"])
    action2 = propose(client, contact)
    decision(client, action2, "approve")
    with factory() as db:
        db.info["org_id"] = account["organization"]["id"]
        db.scalar(select(Membership)).role = "viewer"
        db.commit()
        with pytest.raises(DomainError):
            execute(db, action2["id"])


def test_snooze_and_expiration(client, contact, factory):
    action = propose(client, contact)
    assert (
        decision(
            client, action, "snooze", scheduled_at=(now() + timedelta(days=1)).isoformat()
        ).status_code
        == 200
    )
    with factory() as db:
        row = db.scalar(select(AIAction))
        row.expires_at = now() - timedelta(minutes=1)
        version = row.version
        db.commit()
    assert decision(client, {**action, "version": version}, "approve").status_code == 409


def test_external_missing_credentials_never_claims_sent(client, contact, factory):
    action = propose(
        client,
        contact,
        "send_email",
        {"to": contact["email"], "subject": "Hello", "body": "A reviewed follow-up"},
    )
    decision(client, action, "approve")
    tick()
    with factory() as db:
        row = db.scalar(select(AIAction))
        assert row.status == "failed"
        assert row.error_code == "google_unconfigured"


def test_changed_profile_prevents_undo(client, contact, factory):
    action = propose(client, contact)
    decision(client, action, "approve")
    tick()
    client.put(f"/api/v1/contacts/{contact['id']}/preferences", json={"budget_max": 900000})
    with factory() as db:
        row = db.scalar(select(AIAction))
        version = row.version
    response = decision(client, {**action, "version": version}, "undo")
    assert response.status_code == 409
