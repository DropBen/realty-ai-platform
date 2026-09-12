from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from realty import identity
from realty.config import settings
from realty.db import get_db, now
from realty.errors import DomainError
from realty.models import LoginSession, Membership, OAuthState, Organization, Subscription, User
from realty.repository import public
from realty.schemas import Login, Register
from realty.security import (
    Principal,
    audit,
    hash_password,
    new_session,
    principal,
    rate_limit,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])
_DUMMY_PASSWORD_HASH = hash_password("not-a-real-account-password")


@router.post("/register", status_code=201)
def register(
    data: Register,
    request: Request,
    response: Response,
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    rate_limit(db, "register:" + (request.client.host if request.client else "unknown"), 5)
    db.commit()
    if settings.require_email_verification:
        identity.require_mail()
    if db.scalar(select(User).where(User.email == str(data.email).lower())):
        raise DomainError(
            "account_unavailable", "This email cannot be registered. Try signing in.", 409
        )
    user = User(
        name=data.name, email=str(data.email).lower(), password_hash=hash_password(data.password)
    )
    org = Organization(name=data.organization, is_demo=settings.demo_mode)
    db.add_all([user, org])
    db.flush()
    db.add(Membership(user_id=user.id, org_id=org.id, role="owner"))
    db.add(Subscription(org_id=org.id, trial_end=now() + timedelta(days=14)))
    db.flush()
    if identity.mail_ready():
        identity.request_link(db, user, "verify")
    csrf = new_session(db, user, org, response, request.headers.get("user-agent", ""))
    audit(db, Principal(user.id, org.id, "owner"), "account.created", user.id)
    return {"user": public(user), "organization": public(org), "role": "owner", "csrf_token": csrf}


@router.post("/login")
def login(
    data: Login,
    request: Request,
    response: Response,
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    rate_limit(db, "login:" + (request.client.host if request.client else "unknown"), 10)
    rate_limit(db, "login-account:" + str(data.email).lower(), 30, 15 * 60)
    db.commit()
    user = db.scalar(select(User).where(User.email == str(data.email).lower()).with_for_update())
    # Match password hashing cost for unknown accounts to reduce account enumeration.
    valid = (
        verify_password(data.password, user.password_hash)
        if user
        else verify_password(data.password, _DUMMY_PASSWORD_HASH)
    )
    if not user or not valid:
        raise DomainError("invalid_login", "Email or password is incorrect.", 401)
    if user.mfa_ciphertext:
        response.delete_cookie("realty_session", path="/")
        response.delete_cookie("realty_csrf", path="/")
        challenge = identity.issue_token(db, user, "mfa_login", 5)
        response.set_cookie(
            "realty_mfa",
            challenge,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="strict",
            max_age=300,
            path="/",
        )
        return {"mfa_required": True}
    membership = db.scalar(
        select(Membership).where(Membership.user_id == user.id).order_by(Membership.created_at)
    )
    if not membership:
        raise DomainError("no_organization", "No active organization is available.", 403)
    org = db.get(Organization, membership.org_id)
    assert org is not None
    csrf = new_session(db, user, org, response, request.headers.get("user-agent", ""))
    audit(db, Principal(user.id, org.id, membership.role), "auth.login", user.id)
    return {
        "user": public(user),
        "organization": public(org),
        "role": membership.role,
        "csrf_token": csrf,
    }


@router.get("/me")
def me(
    actor: Principal = Depends(principal), db: Session = Depends(get_db, scope="function")
) -> dict[str, Any]:
    organization = db.get(Organization, actor.org_id)
    return {
        "user": public(db.get(User, actor.user_id)),
        "organization": public(organization),
        "role": actor.role,
        "demo_mode": settings.demo_mode or bool(organization and organization.is_demo),
        "require_email_verification": settings.require_email_verification,
    }


@router.post("/logout")
def logout(
    response: Response,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, bool]:
    db.execute(delete(OAuthState).where(OAuthState.session_id == actor.session_id))
    db.execute(delete(LoginSession).where(LoginSession.id == actor.session_id))
    audit(db, actor, "auth.logout", actor.user_id)
    response.delete_cookie("realty_session", path="/")
    response.delete_cookie("realty_csrf", path="/")
    return {"ok": True}
