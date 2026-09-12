"""Identity workflows with no access to CRM until required factors are complete."""

from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import ConfigDict, EmailStr, Field, model_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from realty import identity
from realty.config import settings
from realty.db import get_db, now
from realty.errors import DomainError
from realty.models import (
    AuthToken,
    LoginSession,
    Membership,
    OAuthState,
    Organization,
    RecoveryCode,
    User,
)
from realty.repository import public
from realty.schemas import Input
from realty.security import Principal, audit, hash_password, new_session, principal, rate_limit

router = APIRouter(prefix="/auth", tags=["Account security"])


class TokenInput(Input):
    token: str = Field(min_length=20, max_length=128)


class EmailInput(Input):
    email: EmailStr


class FactorInput(Input):
    code: str = Field(min_length=6, max_length=40)


class Reauthenticate(Input):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    password: str = Field(min_length=1, max_length=128)
    code: str = Field(default="", max_length=40)


class NewPassword(Input):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    new_password: str = Field(min_length=12, max_length=128)
    confirm_password: str = Field(min_length=12, max_length=128)

    @model_validator(mode="after")
    def matches(self) -> "NewPassword":
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords must match")
        return self


class PasswordChange(NewPassword):
    password: str = Field(min_length=1, max_length=128)
    code: str = Field(default="", max_length=40)


class PasswordReset(NewPassword):
    token: str = Field(min_length=20, max_length=128)
    code: str = Field(default="", max_length=40)


def entry_limit(db: Session, request: Request, action: str, key: str = "") -> None:
    host = request.client.host if request.client else "unknown"
    rate_limit(db, f"identity:{action}:{host}", 10)
    if key:
        rate_limit(db, f"identity:{action}:subject:{key}", 5, 15 * 60)
    db.commit()


def identity_actor(db: Session, user: User) -> Principal:
    columns = Membership.__table__.c
    member = db.execute(
        select(columns.org_id, columns.role)
        .where(columns.user_id == user.id)
        .order_by(columns.created_at)
    ).first()
    if not member:
        raise DomainError("no_organization", "No active organization is available.", 403)
    return Principal(user.id, member.org_id, member.role)


def clear_cookies(response: Response) -> None:
    for cookie in ["realty_session", "realty_csrf", "realty_mfa"]:
        response.delete_cookie(cookie, path="/")


@router.post("/password/request")
def request_password(
    body: EmailInput, request: Request, db: Session = Depends(get_db, scope="function")
) -> dict[str, str]:
    identity.require_mail()
    email = str(body.email).lower()
    entry_limit(db, request, "reset_request", email)
    user = db.scalar(select(User).where(User.email == email).with_for_update())
    if user:
        identity.request_link(db, user, "reset")
        audit(db, identity_actor(db, user), "auth.recovery_requested", user.id)
    return {"message": "If an account is eligible, a recovery email will be delivered."}


@router.post("/password/reset")
def reset_password(
    body: PasswordReset,
    request: Request,
    response: Response,
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, bool]:
    entry_limit(db, request, "reset", body.token)
    user = identity.consume_token(db, body.token, "reset")
    if user.mfa_ciphertext:
        identity.verify_factor(db, user, body.code)
    user.password_hash = hash_password(body.new_password)
    user.email_verified_at = user.email_verified_at or now()
    identity.revoke_sessions(db, user.id)
    db.execute(delete(AuthToken).where(AuthToken.user_id == user.id))
    audit(db, identity_actor(db, user), "auth.password_reset", user.id)
    identity.security_notice(db, user, "password reset")
    clear_cookies(response)
    return {"ok": True}


@router.post("/email/request")
def request_verification(
    request: Request,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, bool]:
    identity.require_mail()
    entry_limit(db, request, "verify_request", actor.user_id)
    user = identity.locked_user(db, actor.user_id)
    if not user.email_verified_at:
        identity.request_link(db, user, "verify")
        audit(db, actor, "auth.verification_requested", user.id)
    return {"ok": True}


@router.post("/email/verify")
def verify_email(
    body: TokenInput, request: Request, db: Session = Depends(get_db, scope="function")
) -> dict[str, bool]:
    entry_limit(db, request, "verify", body.token)
    user = identity.consume_token(db, body.token, "verify")
    user.email_verified_at = now()
    audit(db, identity_actor(db, user), "auth.email_verified", user.id)
    return {"ok": True}


@router.get("/security")
def security_status(
    actor: Principal = Depends(principal), db: Session = Depends(get_db, scope="function")
) -> dict[str, Any]:
    user = identity.locked_user(db, actor.user_id)
    return {
        "email_verified": user.email_verified_at is not None,
        "mfa_enabled": bool(user.mfa_ciphertext),
        "mail_backend": settings.mail_backend if identity.mail_ready() else "disabled",
        "recovery_codes_remaining": db.scalar(
            select(func.count())
            .select_from(RecoveryCode)
            .where(RecoveryCode.user_id == user.id, RecoveryCode.used_at.is_(None))
        )
        or 0,
    }


@router.get("/sessions")
def sessions(
    actor: Principal = Depends(principal), db: Session = Depends(get_db, scope="function")
) -> dict[str, Any]:
    rows = db.scalars(
        select(LoginSession)
        .where(LoginSession.user_id == actor.user_id, LoginSession.expires_at > now())
        .order_by(LoginSession.created_at.desc())
        .limit(100)
    ).all()
    return {
        "items": [
            {
                "id": row.id,
                "created_at": row.created_at,
                "expires_at": row.expires_at,
                "user_agent": row.user_agent,
                "current": row.id == actor.session_id,
            }
            for row in rows
        ]
    }


@router.delete("/sessions/{session_id}")
def revoke_session(
    session_id: str,
    response: Response,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, bool]:
    row = db.scalar(
        select(LoginSession).where(
            LoginSession.id == session_id, LoginSession.user_id == actor.user_id
        )
    )
    if not row:
        raise DomainError("not_found", "This session is unavailable.", 404)
    db.execute(delete(OAuthState).where(OAuthState.session_id == row.id))
    db.delete(row)
    audit(db, actor, "auth.session_revoked", row.id)
    if row.id == actor.session_id:
        clear_cookies(response)
    return {"ok": True}


@router.post("/sessions/revoke-all")
def revoke_all(
    response: Response,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, bool]:
    identity.revoke_sessions(db, actor.user_id)
    audit(db, actor, "auth.sessions_revoked", actor.user_id)
    clear_cookies(response)
    return {"ok": True}


@router.post("/password/change")
def change_password(
    body: PasswordChange,
    request: Request,
    response: Response,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, bool]:
    entry_limit(db, request, "password_change", actor.user_id)
    user = identity.locked_user(db, actor.user_id)
    identity.check_password(user, body.password)
    if user.mfa_ciphertext:
        identity.verify_factor(db, user, body.code)
    user.password_hash = hash_password(body.new_password)
    identity.revoke_sessions(db, user.id)
    db.execute(delete(AuthToken).where(AuthToken.user_id == user.id))
    audit(db, actor, "auth.password_changed", user.id)
    identity.security_notice(db, user, "password changed")
    clear_cookies(response)
    return {"ok": True}


@router.post("/mfa/enroll")
def enroll(
    body: Reauthenticate,
    request: Request,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, str]:
    entry_limit(db, request, "mfa_enroll", actor.user_id)
    user = identity.locked_user(db, actor.user_id)
    identity.check_password(user, body.password)
    result = identity.new_totp(user)
    audit(db, actor, "auth.mfa_enrollment_started", user.id)
    return result


@router.post("/mfa/confirm")
def confirm_mfa(
    body: FactorInput,
    request: Request,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    entry_limit(db, request, "mfa_confirm", actor.user_id)
    user = identity.locked_user(db, actor.user_id)
    if user.mfa_ciphertext:
        raise DomainError("mfa_enabled", "An authenticator is already active.", 409)
    identity.verify_factor(db, user, body.code, pending=True)
    user.mfa_ciphertext = user.mfa_pending_ciphertext
    user.mfa_pending_ciphertext, user.mfa_pending_until = None, None
    codes = identity.recovery_codes(db, user)
    identity.revoke_sessions(db, user.id, keep=actor.session_id)
    session = db.get(LoginSession, actor.session_id)
    assert session is not None
    session.mfa_verified_at = now()
    audit(db, actor, "auth.mfa_enabled", user.id)
    identity.security_notice(db, user, "authenticator enabled; other sessions revoked")
    return {"recovery_codes": codes}


@router.post("/mfa/verify")
def login_factor(
    body: FactorInput,
    request: Request,
    response: Response,
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    challenge = request.cookies.get("realty_mfa", "")
    entry_limit(db, request, "mfa_login", challenge)
    user = identity.consume_token(db, challenge, "mfa_login")
    identity.verify_factor(db, user, body.code)
    actor = identity_actor(db, user)
    org = db.get(Organization, actor.org_id)
    assert org is not None
    csrf = new_session(db, user, org, response, request.headers.get("user-agent", ""), True)
    response.delete_cookie("realty_mfa", path="/")
    audit(db, actor, "auth.login_mfa", user.id)
    return {
        "user": public(user),
        "organization": public(org),
        "role": actor.role,
        "csrf_token": csrf,
    }


@router.post("/mfa/disable")
def disable_mfa(
    body: Reauthenticate,
    request: Request,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, bool]:
    entry_limit(db, request, "mfa_disable", actor.user_id)
    user = identity.locked_user(db, actor.user_id)
    identity.check_password(user, body.password)
    identity.verify_factor(db, user, body.code)
    user.mfa_ciphertext, user.mfa_pending_ciphertext, user.mfa_pending_until = None, None, None
    db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    identity.revoke_sessions(db, user.id, keep=actor.session_id)
    audit(db, actor, "auth.mfa_disabled", user.id)
    identity.security_notice(db, user, "authenticator disabled; other sessions revoked")
    return {"ok": True}


@router.post("/mfa/recovery-codes")
def rotate_codes(
    body: Reauthenticate,
    request: Request,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    entry_limit(db, request, "recovery_codes", actor.user_id)
    user = identity.locked_user(db, actor.user_id)
    identity.check_password(user, body.password)
    identity.verify_factor(db, user, body.code)
    codes = identity.recovery_codes(db, user)
    audit(db, actor, "auth.recovery_codes_rotated", user.id)
    identity.security_notice(db, user, "recovery codes replaced")
    return {"recovery_codes": codes}
