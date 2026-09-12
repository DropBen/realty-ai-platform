"""Account recovery, second factors and transactional account mail.

Tokens and factors belong to a user identity across organizations. Every lookup
here therefore names the user or an unguessable token; tenant APIs cannot list
these tables. External mail is requested only by an account security workflow.
"""

import base64
import hmac
import secrets
import smtplib
import ssl
import time
from datetime import timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.twofactor.totp import TOTP
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from realty.config import settings
from realty.db import now
from realty.errors import DomainError
from realty.models import (
    AccountMail,
    AuthToken,
    LoginSession,
    Membership,
    OAuthState,
    RecoveryCode,
    User,
)
from realty.security import digest, require_live_organization, verify_password


def cipher() -> Fernet:
    if not settings.encryption_key:
        raise DomainError(
            "security_unconfigured", "Account security requires an encryption key.", 503
        )
    return Fernet(settings.encryption_key.encode())


def mail_ready() -> bool:
    return bool(
        settings.encryption_key
        and (
            settings.mail_backend == "outbox"
            and settings.app_env != "production"
            or settings.mail_backend == "smtp"
            and settings.smtp_host
            and not settings.demo_mode
        )
    )


def require_mail() -> None:
    if not mail_ready():
        raise DomainError("mail_unconfigured", "Account email delivery is not configured.", 503)


def locked_user(db: Session, user_id: str) -> User:
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if not user:
        raise DomainError("unauthenticated", "Sign in to continue.", 401)
    return user


def check_password(user: User, password: str) -> None:
    if not verify_password(password, user.password_hash):
        raise DomainError("confirmation_failed", "Your current password is incorrect.", 403)


def issue_token(db: Session, user: User, purpose: str, minutes: int) -> str:
    # One active token per purpose prevents an old link surviving a newer request.
    db.execute(delete(AuthToken).where(AuthToken.user_id == user.id, AuthToken.purpose == purpose))
    value = secrets.token_urlsafe(32)
    db.add(
        AuthToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=digest(value),
            expires_at=now() + timedelta(minutes=minutes),
        )
    )
    db.flush()
    return value


def consume_token(db: Session, value: str, purpose: str) -> User:
    token = db.scalar(
        select(AuthToken).where(AuthToken.token_hash == digest(value), AuthToken.purpose == purpose)
    )
    if not token or token.consumed_at or token.expires_at <= now():
        raise DomainError(
            "invalid_token", "This link or sign-in request is invalid or has expired.", 400
        )
    user = locked_user(db, token.user_id)
    claimed = db.scalar(
        update(AuthToken)
        .where(
            AuthToken.id == token.id,
            AuthToken.consumed_at.is_(None),
            AuthToken.expires_at > now(),
        )
        .values(consumed_at=now())
        .returning(AuthToken.id)
    )
    if not claimed:
        raise DomainError("invalid_token", "This link has already been used.", 400)
    return user


def revoke_sessions(db: Session, user_id: str, keep: str | None = None) -> None:
    statement = select(LoginSession.id).where(LoginSession.user_id == user_id)
    if keep:
        statement = statement.where(LoginSession.id != keep)
    db.execute(delete(OAuthState).where(OAuthState.session_id.in_(statement)))
    db.execute(delete(LoginSession).where(LoginSession.id.in_(statement)))
    db.execute(
        delete(AuthToken).where(AuthToken.user_id == user_id, AuthToken.purpose == "mfa_login")
    )


def totp_code(secret: str, counter: int, digits: int = 6) -> str:
    key = base64.b32decode(secret)
    # RFC 6238 HMAC-SHA1 for authenticator compatibility, not a password hash.
    return TOTP(key, digits, hashes.SHA1(), 30).generate(counter * 30).decode()  # nosec B303


def new_totp(user: User) -> dict[str, str]:
    if user.mfa_ciphertext:
        raise DomainError(
            "mfa_enabled", "Disable the current authenticator before replacing it.", 409
        )
    key = secrets.token_bytes(20)
    secret = base64.b32encode(key).decode()
    user.mfa_pending_ciphertext = cipher().encrypt(secret.encode()).decode()
    user.mfa_pending_until = now() + timedelta(minutes=10)
    return {
        "secret": secret,
        "uri": TOTP(key, 6, hashes.SHA1(), 30).get_provisioning_uri(user.email, "RealtyAI"),  # nosec B303
    }


def verify_factor(db: Session, user: User, code: str, pending: bool = False) -> None:
    encrypted = user.mfa_pending_ciphertext if pending else user.mfa_ciphertext
    if not encrypted or (
        pending and (not user.mfa_pending_until or user.mfa_pending_until <= now())
    ):
        raise DomainError("mfa_unavailable", "Start authenticator enrollment again.", 400)
    cleaned = code.replace(" ", "").replace("-", "").lower()
    if not pending and len(cleaned) == 24:
        used = db.scalar(
            update(RecoveryCode)
            .where(
                RecoveryCode.user_id == user.id,
                RecoveryCode.code_hash == digest(cleaned),
                RecoveryCode.used_at.is_(None),
            )
            .values(used_at=now())
            .returning(RecoveryCode.id)
        )
        if used:
            return
    secret = cipher().decrypt(encrypted.encode()).decode()
    counter = int(time.time()) // 30
    for candidate in [counter - 1, counter, counter + 1]:
        if candidate <= user.mfa_last_counter and not pending:
            continue
        if hmac.compare_digest(totp_code(secret, candidate), cleaned):
            claimed = db.scalar(
                update(User)
                .where(
                    User.id == user.id,
                    User.mfa_last_counter < candidate,
                )
                .values(mfa_last_counter=candidate)
                .returning(User.id)
            )
            if claimed:
                user.mfa_last_counter = candidate
                return
    raise DomainError(
        "invalid_factor", "The authentication or recovery code is invalid or already used.", 401
    )


def recovery_codes(db: Session, user: User) -> list[str]:
    db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    values = [secrets.token_hex(12) for _ in range(10)]
    db.add_all([RecoveryCode(user_id=user.id, code_hash=digest(value)) for value in values])
    return ["-".join(value[i : i + 6] for i in range(0, 24, 6)) for value in values]


def queue_mail(db: Session, user: User, purpose: str, body: str) -> None:
    require_mail()
    # Core identity query is intentionally user-scoped across all memberships.
    table = Membership.__table__.c
    org_id = db.info.get("org_id") or db.scalar(
        select(table.org_id).where(table.user_id == user.id).order_by(table.created_at)
    )
    if not org_id:
        raise DomainError("no_organization", "No active organization is available.", 403)
    if settings.mail_backend == "smtp":
        require_live_organization(db, org_id)
    mail = AccountMail(
        user_id=user.id, purpose=purpose, body_ciphertext=cipher().encrypt(body.encode()).decode()
    )
    db.add(mail)
    db.flush()
    from realty.jobs import enqueue

    enqueue(db, org_id, "account_mail", {"user_id": user.id, "mail_id": mail.id}, "mail:" + mail.id)


def request_link(db: Session, user: User, purpose: str) -> None:
    value = issue_token(db, user, purpose, 30 if purpose == "reset" else 60 * 24)
    # A fragment is never sent in a request line, Referer header or proxy access log.
    url = settings.app_origin.rstrip("/") + "/account-access#" + purpose + "=" + value
    label = "Reset your password" if purpose == "reset" else "Verify your email address"
    queue_mail(
        db,
        user,
        purpose,
        f"{label}\n\n{url}\n\nThis link is single-use. If you did not request it, ignore this message.",
    )


def security_notice(db: Session, user: User, event: str) -> None:
    if mail_ready():
        queue_mail(
            db,
            user,
            "security",
            f"Your RealtyAI account security changed: {event}.\nIf this was not you, use account recovery immediately.",
        )


def deliver_mail(db: Session, payload: dict[str, Any]) -> None:
    require_mail()
    if settings.mail_backend == "smtp":
        require_live_organization(db, str(db.info.get("org_id", "")))
    mail = db.scalar(
        select(AccountMail).where(
            AccountMail.id == payload.get("mail_id"), AccountMail.user_id == payload.get("user_id")
        )
    )
    if not mail or mail.sent_at or not mail.body_ciphertext:
        return
    user = db.get(User, mail.user_id)
    if not user:
        return
    message = EmailMessage()
    message["From"], message["To"] = settings.mail_from, user.email
    message["Subject"] = {
        "reset": "Reset your RealtyAI password",
        "verify": "Verify your RealtyAI email",
    }.get(mail.purpose, "RealtyAI account security")
    message["Message-ID"] = f"<{mail.id}@realtyai-account>"
    message.set_content(cipher().decrypt(mail.body_ciphertext.encode()).decode())
    try:
        if settings.mail_backend == "outbox":
            directory = Path(settings.mail_outbox_path).resolve()
            directory.mkdir(parents=True, exist_ok=True)
            (directory / f"{mail.id}.eml").write_bytes(message.as_bytes())
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
                if settings.smtp_starttls:
                    smtp.starttls(context=ssl.create_default_context())
                if settings.smtp_username:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise DomainError(
            "mail_delivery_failed", "Account email delivery will be retried.", 503
        ) from exc
    # Remove token-bearing bodies after delivery. Retries may deliver the same
    # message twice after a crash; the underlying token remains single-use.
    mail.sent_at, mail.body_ciphertext = now(), None
