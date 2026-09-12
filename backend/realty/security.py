import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from fastapi import Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from realty.config import settings
from realty.db import get_db, now
from realty.errors import DomainError
from realty.models import Audit, LoginSession, Membership, Organization, RateBucket, User

ROLE_PERMISSIONS = {
    "owner": {"read", "write", "approve", "external", "billing", "members", "delete_org"},
    "admin": {"read", "write", "approve", "external", "billing", "members"},
    "agent": {"read", "write", "approve", "external"},
    "assistant": {"read", "write"},
    "viewer": {"read"},
}


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    value = hashlib.scrypt(
        password.encode(), salt=salt.encode(), n=2**15, r=8, p=1, maxmem=64 * 1024 * 1024
    )
    return f"scrypt${salt}${value.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, expected = stored.split("$")
        actual = hashlib.scrypt(
            password.encode(), salt=salt.encode(), n=2**15, r=8, p=1, maxmem=64 * 1024 * 1024
        )
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


@dataclass
class Principal:
    user_id: str
    org_id: str
    role: str
    session_id: str = ""

    def require(self, permission: str) -> None:
        if permission not in ROLE_PERMISSIONS.get(self.role, set()):
            raise DomainError("forbidden", "Your role does not allow this action.", 403)


def audit(
    db: Session,
    actor: Principal,
    action: str,
    target: str | None = None,
    details: dict[str, Any] | None = None,
    result: str = "success",
) -> None:
    db.add(
        Audit(
            org_id=actor.org_id,
            actor_id=actor.user_id,
            action=action,
            target_id=target,
            result=result,
            details=details or {},
        )
    )


def rate_limit(db: Session, key: str, limit: int = 120) -> None:
    """Database-backed fixed window. Lock protects counts across API instances."""
    window = int(time.time()) // 60
    bucket = db.scalar(select(RateBucket).where(RateBucket.key == key).with_for_update())
    if not bucket:
        db.add(RateBucket(key=key, window=window, count=1))
    elif bucket.window != window:
        bucket.window, bucket.count = window, 1
    elif bucket.count >= limit:
        raise DomainError("rate_limited", "Too many requests. Try again in a minute.", 429)
    else:
        bucket.count += 1
    db.flush()


def principal(request: Request, db: Session = Depends(get_db, scope="function")) -> Principal:
    token = request.cookies.get("realty_session", "")
    session = db.scalar(
        select(LoginSession).where(
            LoginSession.token_hash == digest(token), LoginSession.expires_at > now()
        )
    )
    if not session:
        raise DomainError("unauthenticated", "Sign in to continue.", 401)
    membership = db.scalar(
        select(Membership).where(
            Membership.org_id == session.org_id, Membership.user_id == session.user_id
        )
    )
    if not membership:
        raise DomainError("forbidden", "Organization access has been removed.", 403)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(digest(csrf), session.csrf_hash):
            raise DomainError("csrf", "Session verification failed. Refresh and try again.", 403)
    db.info["org_id"] = session.org_id
    rate_limit(db, "user:" + session.user_id)
    return Principal(session.user_id, session.org_id, membership.role, session.id)


def new_session(db: Session, user: User, org: Organization, response: Response) -> str:
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    db.add(
        LoginSession(
            user_id=user.id,
            org_id=org.id,
            token_hash=digest(token),
            csrf_hash=digest(csrf),
            expires_at=now() + timedelta(hours=settings.session_hours),
        )
    )
    response.set_cookie(
        "realty_session",
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_hours * 3600,
        path="/",
    )
    response.set_cookie(
        "realty_csrf",
        csrf,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_hours * 3600,
        path="/",
    )
    return csrf
