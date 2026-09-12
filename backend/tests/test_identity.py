import base64
import re
import secrets
import shutil
import time
from datetime import timedelta
from pathlib import Path

import pytest
from conftest import register
from cryptography.fernet import Fernet
from realty import identity
from realty.config import settings
from realty.db import now
from realty.jobs import tick
from realty.models import AccountMail, AuthToken, LoginSession, RecoveryCode, User
from sqlalchemy import select


@pytest.fixture
def account_mail(monkeypatch):
    directory = Path("data") / ("test-account-mail-" + secrets.token_hex(8))
    directory.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "mail_backend", "outbox")
    monkeypatch.setattr(settings, "mail_outbox_path", str(directory.resolve()))
    yield directory
    shutil.rmtree(directory)


def link_token(factory, purpose):
    with factory() as db:
        mail = db.scalar(
            select(AccountMail)
            .where(AccountMail.purpose == purpose)
            .order_by(AccountMail.created_at.desc())
        )
        assert mail and mail.body_ciphertext
        body = identity.cipher().decrypt(mail.body_ciphertext.encode()).decode()
        assert body not in mail.body_ciphertext
        return re.search(r"#(?:reset|verify)=([\w-]+)", body).group(1)


def test_email_verification_gates_crm_and_tokens_are_one_use(
    client, factory, account_mail, monkeypatch
):
    monkeypatch.setattr(settings, "require_email_verification", True)
    account = register(client)
    assert account["user"]["email_verified_at"] is None
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.get("/api/v1/crm/contacts").status_code == 403
    token = link_token(factory, "verify")
    assert tick()
    assert list(account_mail.glob("*.eml"))
    with factory() as db:
        mail = db.scalar(select(AccountMail))
        assert mail.sent_at and mail.body_ciphertext is None
        assert token not in db.scalar(select(AuthToken)).token_hash
    assert client.post("/api/v1/auth/email/verify", json={"token": token}).status_code == 200
    assert client.get("/api/v1/crm/contacts").status_code == 200
    assert client.post("/api/v1/auth/email/verify", json={"token": token}).status_code == 400


def test_recovery_is_generic_expires_and_revokes_every_session(client, factory, account_mail):
    register(client)
    response = client.post("/api/v1/auth/password/request", json={"email": "agent-one@example.com"})
    unknown = client.post("/api/v1/auth/password/request", json={"email": "absent@example.com"})
    assert response.status_code == unknown.status_code == 200
    assert response.json() == unknown.json()
    token = link_token(factory, "reset")
    body = {
        "token": token,
        "new_password": "changed-password-123",
        "confirm_password": "changed-password-123",
    }
    with factory() as db:
        row = db.scalar(select(AuthToken).where(AuthToken.purpose == "reset"))
        row.expires_at = now() - timedelta(seconds=1)
        db.commit()
    assert client.post("/api/v1/auth/password/reset", json=body).status_code == 400
    assert (
        client.post(
            "/api/v1/auth/password/request", json={"email": "agent-one@example.com"}
        ).status_code
        == 200
    )
    body["token"] = link_token(factory, "reset")
    assert client.post("/api/v1/auth/password/reset", json=body).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/auth/password/reset", json=body).status_code == 400
    with factory() as db:
        assert not db.scalars(select(LoginSession)).all()
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "agent-one@example.com", "password": "secure-password-123!"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "agent-one@example.com", "password": body["new_password"]},
        ).status_code
        == 200
    )


def enroll(client):
    result = client.post("/api/v1/auth/mfa/enroll", json={"password": "secure-password-123!"})
    assert result.status_code == 200, result.text
    secret = result.json()["secret"]
    code = identity.totp_code(secret, int(time.time()) // 30)
    result = client.post("/api/v1/auth/mfa/confirm", json={"code": code})
    assert result.status_code == 200, result.text
    return secret, code, result.json()["recovery_codes"]


def login(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "agent-one@example.com", "password": "secure-password-123!"},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"mfa_required": True}
    assert client.get("/api/v1/auth/me").status_code == 401


def test_mfa_enrollment_replay_recovery_and_secret_redaction(
    client, factory, account, account_mail
):
    secret, code, codes = enroll(client)
    assert len(codes) == 10
    me = client.get("/api/v1/auth/me")
    assert me.json()["user"]["mfa_enabled"] is True
    assert "ciphertext" not in me.text and secret not in me.text
    with factory() as db:
        assert secret not in db.get(User, account["user"]["id"]).mfa_ciphertext
        hashes = [row.code_hash for row in db.scalars(select(RecoveryCode))]
        assert not any(value.replace("-", "") in hashes for value in codes)
    assert client.post("/api/v1/auth/logout").status_code == 200
    login(client)
    assert client.post("/api/v1/auth/mfa/verify", json={"code": code}).status_code == 401
    result = client.post("/api/v1/auth/mfa/verify", json={"code": codes[0]})
    assert result.status_code == 200, result.text
    client.headers["x-csrf-token"] = result.json()["csrf_token"]
    assert client.get("/api/v1/crm/contacts").status_code == 200
    assert client.post("/api/v1/auth/mfa/verify", json={"code": codes[1]}).status_code == 400
    assert client.post("/api/v1/auth/logout").status_code == 200
    login(client)
    assert client.post("/api/v1/auth/mfa/verify", json={"code": codes[0]}).status_code == 401
    result = client.post("/api/v1/auth/mfa/verify", json={"code": codes[1]})
    assert result.status_code == 200
    client.headers["x-csrf-token"] = result.json()["csrf_token"]
    assert (
        client.post(
            "/api/v1/auth/mfa/disable", json={"password": "secure-password-123!", "code": codes[2]}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/auth/security").json()["mfa_enabled"] is False


def test_reset_does_not_bypass_mfa(client, factory, account, account_mail):
    _, _, codes = enroll(client)
    client.post("/api/v1/auth/password/request", json={"email": "agent-one@example.com"})
    body = {
        "token": link_token(factory, "reset"),
        "new_password": "replacement-password-123",
        "confirm_password": "replacement-password-123",
    }
    assert client.post("/api/v1/auth/password/reset", json=body).status_code == 401
    assert (
        client.post("/api/v1/auth/password/reset", json={**body, "code": codes[0]}).status_code
        == 200
    )
    result = client.post(
        "/api/v1/auth/login",
        json={"email": "agent-one@example.com", "password": body["new_password"]},
    )
    assert result.json() == {"mfa_required": True}


def test_session_ownership_and_password_change_invalidation(client, factory, account):
    first_id = client.get("/api/v1/auth/sessions").json()["items"][0]["id"]
    register(client, "two")
    assert client.delete("/api/v1/auth/sessions/" + first_id).status_code == 404
    result = client.post(
        "/api/v1/auth/password/change",
        json={
            "password": "secure-password-123!",
            "new_password": "new-second-password-123",
            "confirm_password": "new-second-password-123",
        },
    )
    assert result.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
    with factory() as db:
        assert db.get(LoginSession, first_id) is not None


def test_failed_reauthentication_is_rate_limited(client, account):
    for _ in range(5):
        assert (
            client.post("/api/v1/auth/mfa/enroll", json={"password": "wrong-password"}).status_code
            == 403
        )
    assert (
        client.post("/api/v1/auth/mfa/enroll", json={"password": "wrong-password"}).status_code
        == 429
    )


def test_totp_matches_rfc6238_vectors():
    key = base64.b32encode(b"12345678901234567890").decode()
    for seconds, expected in [
        (59, "94287082"),
        (1111111109, "07081804"),
        (1111111111, "14050471"),
        (1234567890, "89005924"),
        (2000000000, "69279037"),
    ]:
        assert identity.totp_code(key, seconds // 30, 8) == expected


def test_organization_deletion_requires_current_factor(client, account, account_mail):
    _, _, codes = enroll(client)
    body = {
        "organization_name": account["organization"]["name"],
        "password": "secure-password-123!",
    }
    assert client.post("/api/v1/account/delete", json=body).status_code == 401
    result = client.post("/api/v1/account/delete", json={**body, "code": codes[0]})
    assert result.status_code == 200, result.text
    assert client.get("/api/v1/auth/me").status_code == 401
