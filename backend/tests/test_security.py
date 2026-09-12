import pytest
from conftest import register
from realty.config import Settings
from realty.errors import DomainError
from realty.models import Contact, Membership, Task
from realty.security import Principal, hash_password, verify_password
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


def test_password_hashes_are_salted():
    first, second = hash_password("password123456"), hash_password("password123456")
    assert first != second
    assert verify_password("password123456", first)
    assert not verify_password("wrong", first)


def test_anonymous_cannot_read(client):
    assert client.get("/api/v1/crm/contacts").status_code == 401


def test_csrf_and_origin(client, account):
    client.headers.pop("x-csrf-token")
    assert client.post("/api/v1/crm/contacts", json={"name": "No CSRF"}).status_code == 403
    assert (
        client.post(
            "/api/v1/auth/login",
            headers={"origin": "https://evil.example"},
            json={"email": "agent-one@example.com", "password": "secure-password-123!"},
        ).status_code
        == 403
    )


def test_tenant_isolation_read_write_search_and_analytics(client, account, contact):
    first_id = contact["id"]
    register(client, "two")
    assert client.get("/api/v1/crm/contacts").json()["total"] == 0
    assert client.get("/api/v1/crm/contacts/" + first_id).status_code == 404
    assert client.get("/api/v1/contacts/" + first_id + "/profile").status_code == 404
    assert (
        client.put("/api/v1/crm/contacts/" + first_id, json={"name": "Stolen"}).status_code == 404
    )
    assert (
        client.post(
            "/api/v1/crm/tasks", json={"title": "Cross-tenant", "contact_id": first_id}
        ).status_code
        == 404
    )
    result = client.post("/api/v1/command", json={"question": "Show all buyers"}).json()
    assert result["records"] == []
    assert client.get("/api/v1/briefing").json()["contacts"] == 0
    assert client.get("/api/v1/analytics").json()["pipeline"] == []


def test_composite_foreign_keys_enforce_tenant_boundary(factory, client, contact):
    second = register(client, "two")
    with factory() as db:
        db.add(
            Task(
                org_id=second["organization"]["id"],
                contact_id=contact["id"],
                title="Invalid tenant relation",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_orm_write_guard(factory, client, contact):
    second = register(client, "two")
    with factory() as db:
        db.info["org_id"] = second["organization"]["id"]
        db.add(Contact(org_id="wrong", name="Wrong tenant"))
        with pytest.raises(ValueError, match="Tenant boundary"):
            db.flush()


def test_viewer_cannot_mutate(client, factory, account):
    with factory() as db:
        member = db.scalar(select(Membership).where(Membership.user_id == account["user"]["id"]))
        member.role = "viewer"
        db.commit()
    assert client.get("/api/v1/crm/contacts").status_code == 200
    assert client.post("/api/v1/crm/contacts", json={"name": "Forbidden"}).status_code == 403
    assert client.get("/api/v1/billing").status_code == 403


@pytest.mark.parametrize("role", ["viewer", "assistant"])
def test_roles_cannot_approve(role):
    with pytest.raises(DomainError):
        Principal("u", "o", role).require("approve")


def test_invalid_data_and_sql_input(client, contact):
    assert (
        client.post("/api/v1/crm/contacts", json={"name": "A", "org_id": "forged"}).status_code
        == 422
    )
    assert (
        client.put(
            f"/api/v1/contacts/{contact['id']}/preferences",
            json={"budget_min": 800000, "budget_max": 100000},
        ).status_code
        == 422
    )
    assert client.get("/api/v1/crm/contacts?q=' OR 1=1--").json()["total"] == 0
    assert client.get("/api/v1/crm/contacts?sort=password_hash").status_code == 422


def test_production_configuration_fails_closed():
    with pytest.raises(ValueError):
        Settings(app_env="production", demo_mode=True)
    with pytest.raises(ValueError):
        Settings(app_env="production", demo_mode=False, cookie_secure=False)


def test_error_response_never_exposes_sensitive_validation_input(client):
    response = client.post("/api/v1/auth/register", json={"password": "my-secret"})
    assert "my-secret" not in response.text


def test_security_headers_and_cookie(client, account):
    response = client.get("/api/v1/auth/me")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"
    assert len(response.headers["x-request-id"]) == 36
