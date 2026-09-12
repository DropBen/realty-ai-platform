from datetime import datetime, timedelta

import pytest
import respx
import test_integrations as integration_fixtures
from realty.jobs import tick
from realty.models import Activity, AIAction, Appointment
from sqlalchemy import select
from test_actions import decision, propose

configured_google = integration_fixtures.configured_google
EVENT_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events/event1"


@pytest.fixture
def appointment(factory, configured_google, contact):
    with factory() as db:
        row = Appointment(
            org_id=configured_google.org_id,
            owner_id=configured_google.user_id,
            contact_id=contact["id"],
            title="Original showing",
            start_at=datetime(2027, 1, 1, 12),
            end_at=datetime(2027, 1, 1, 13),
            calendar_id="primary",
            external_id=configured_google.user_id + ":primary:event1",
            provider_etag='"revision-1"',
        )
        db.add(row)
        db.commit()
        return row


def calendar_proposal(client, contact, appointment, kind):
    payload = {"appointment_id": appointment.id}
    if kind == "calendar_update":
        payload["event"] = {
            "title": "Reviewed showing",
            "contact_id": contact["id"],
            "start_at": (appointment.start_at + timedelta(hours=2)).isoformat(),
            "end_at": (appointment.end_at + timedelta(hours=2)).isoformat(),
        }
    action = propose(client, contact, kind, payload)
    response = decision(client, action, "approve")
    assert response.status_code == 200, response.text
    return action


@pytest.mark.parametrize("kind", ["calendar_update", "calendar_delete"])
def test_calendar_writes_use_reviewed_provider_revision(
    client, contact, appointment, factory, kind
):
    action = calendar_proposal(client, contact, appointment, kind)
    with respx.mock:
        route = respx.request(
            "PATCH" if kind == "calendar_update" else "DELETE", EVENT_URL
        ).respond(
            200 if kind == "calendar_update" else 204,
            **(
                {"json": {"id": "event1", "etag": '"revision-2"'}}
                if kind == "calendar_update"
                else {}
            ),
        )
        assert tick()
        assert route.call_count == 1
        assert route.calls[0].request.headers["If-Match"] == '"revision-1"'
    with factory() as db:
        assert db.get(AIAction, action["id"]).status == "succeeded"
        row = db.get(Appointment, appointment.id)
        if kind == "calendar_update":
            assert row.title == "Reviewed showing" and row.provider_etag == '"revision-2"'
        else:
            assert row.status == "cancelled"
        assert (
            db.scalar(select(Activity).where(Activity.source_id == action["id"])).contact_id
            == contact["id"]
        )


@pytest.mark.parametrize("kind", ["calendar_update", "calendar_delete"])
@pytest.mark.parametrize("change", ["local", "provider", "missing_revision"])
def test_stale_or_unversioned_calendar_approval_cannot_overwrite_event(
    client, contact, appointment, factory, kind, change
):
    if change == "missing_revision":
        with factory() as db:
            db.get(Appointment, appointment.id).provider_etag = None
            db.commit()
    action = calendar_proposal(client, contact, appointment, kind)
    if change == "local":
        with factory() as db:
            db.get(Appointment, appointment.id).title = "Someone rescheduled this"
            db.commit()
    with respx.mock(assert_all_called=False) as router:
        route = router.request(
            "PATCH" if kind == "calendar_update" else "DELETE", EVENT_URL
        ).respond(412)
        assert tick()
        assert route.call_count == (1 if change == "provider" else 0)
    with factory() as db:
        row = db.get(AIAction, action["id"])
        assert row.status == "failed"
        assert row.error_code == (
            "calendar_sync_required" if change == "missing_revision" else "calendar_changed"
        )
        assert db.get(Appointment, appointment.id).status == "confirmed"
        assert db.scalar(select(Activity).where(Activity.source_id == action["id"])) is None
