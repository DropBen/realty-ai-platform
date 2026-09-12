import base64
import json
import secrets
import time
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Any
from urllib.parse import quote, urlencode

import httpx
from cryptography.fernet import Fernet
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from realty.config import settings
from realty.db import now
from realty.errors import DomainError
from realty.models import (
    Activity,
    AIAction,
    Appointment,
    Communication,
    Contact,
    Integration,
    Job,
    OAuthState,
    SyncCursor,
)
from realty.repository import require
from realty.schemas import AppointmentInput
from realty.security import Principal, audit, digest

SCOPES = {
    "read": [
        "openid",
        "email",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/calendar.readonly",
    ],
    "send": ["https://www.googleapis.com/auth/gmail.send"],
    "calendar_write": ["https://www.googleapis.com/auth/calendar.events"],
}


def configured() -> bool:
    return bool(
        settings.google_client_id
        and settings.google_client_secret
        and settings.encryption_key
        and not settings.demo_mode
    )


def cipher() -> Fernet:
    if not settings.encryption_key:
        raise DomainError("google_unconfigured", "Google integration is not configured.", 503)
    return Fernet(settings.encryption_key.encode())


def authorize(db: Session, actor: Principal, capability: str) -> str:
    actor.require("external")
    if not configured():
        raise DomainError("google_unconfigured", "Google integration is not configured.", 503)
    if capability not in SCOPES:
        raise DomainError("invalid_scope", "Unknown Google capability.")
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(bytes.fromhex(digest(verifier))).rstrip(b"=").decode()
    db.add(
        OAuthState(
            state_hash=digest(state),
            session_id=actor.session_id,
            verifier=verifier,
            expires_at=now() + timedelta(minutes=10),
        )
    )
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES["read"] + SCOPES[capability]),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
        }
    )


def token_request(values: dict[str, str]) -> dict[str, Any]:
    try:
        response = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                **values,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
            },
            timeout=20,
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]
    except (httpx.HTTPError, ValueError) as exc:
        raise DomainError(
            "google_auth_failed", "Google authorization failed. Reconnect your account.", 502
        ) from exc


def callback(db: Session, actor: Principal, code: str, state: str) -> None:
    if not configured():
        raise DomainError("google_unconfigured", "Google integration is not configured.", 503)
    stored = db.scalar(
        select(OAuthState)
        .where(
            OAuthState.state_hash == digest(state),
            OAuthState.session_id == actor.session_id,
            OAuthState.expires_at > now(),
        )
        .with_for_update()
    )
    if not stored:
        raise DomainError(
            "oauth_state", "This Google connection request expired or was already used.", 400
        )
    verifier = stored.verifier
    deleted = db.execute(delete(OAuthState).where(OAuthState.id == stored.id))
    if deleted.rowcount != 1:  # type: ignore[attr-defined]
        raise DomainError("oauth_state", "Google connection request was already used.")
    db.commit()
    tokens = token_request(
        {
            "code": code,
            "code_verifier": verifier,
            "grant_type": "authorization_code",
            "redirect_uri": settings.google_redirect_uri,
        }
    )
    try:
        profile_response = httpx.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": "Bearer " + tokens["access_token"]},
            timeout=20,
        )
        profile_response.raise_for_status()
        profile = profile_response.json()
        if not profile.get("email_verified"):
            raise DomainError("google_identity", "Google did not verify this email address.")
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise DomainError("google_identity", "Could not verify the Google account.", 502) from exc
    integration = db.scalar(
        select(Integration).where(
            Integration.user_id == actor.user_id, Integration.provider == "google"
        )
    )
    if integration and integration.email != profile["email"]:
        raise DomainError(
            "account_mismatch",
            "Disconnect the existing Google account before connecting another.",
            409,
        )
    if not integration:
        integration = Integration(org_id=actor.org_id, user_id=actor.user_id)
        db.add(integration)
    elif integration.token_ciphertext and not tokens.get("refresh_token"):
        old = json.loads(cipher().decrypt(integration.token_ciphertext.encode()))
        tokens["refresh_token"] = old.get("refresh_token")
    tokens["expires_at"] = time.time() + tokens.get("expires_in", 3600)
    integration.token_ciphertext = cipher().encrypt(json.dumps(tokens).encode()).decode()
    integration.email = profile["email"]
    integration.scopes = tokens.get("scope", "")
    integration.status, integration.last_error = "connected", None
    audit(db, actor, "google.connected", integration.id)


class GoogleClient:
    def __init__(self, db: Session, actor: Principal):
        if not configured():
            raise DomainError("google_unconfigured", "Google integration is not configured.", 503)
        self.db = db
        integration = db.scalar(
            select(Integration)
            .where(
                Integration.user_id == actor.user_id,
                Integration.provider == "google",
                Integration.status == "connected",
            )
            .with_for_update()
        )
        if not integration or not integration.token_ciphertext:
            raise DomainError("google_disconnected", "Connect your Google account first.", 409)
        self.integration = integration
        tokens = json.loads(cipher().decrypt(integration.token_ciphertext.encode()))
        if tokens.get("expires_at", 0) <= time.time() + 60:
            if not tokens.get("refresh_token"):
                raise DomainError(
                    "google_reconnect", "Your Google account needs to be reconnected.", 409
                )
            refreshed = token_request(
                {"refresh_token": tokens["refresh_token"], "grant_type": "refresh_token"}
            )
            tokens.update(refreshed)
            tokens["expires_at"] = time.time() + refreshed.get("expires_in", 3600)
            integration.token_ciphertext = cipher().encrypt(json.dumps(tokens).encode()).decode()
            db.flush()
        self.access_token = tokens["access_token"]

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not path.startswith(("gmail/v1/", "calendar/v3/")) or ".." in path:
            raise DomainError("invalid_google_path", "Unsupported Google resource.")
        for attempt in range(3 if method == "GET" else 1):
            try:
                response = httpx.request(
                    method,
                    "https://www.googleapis.com/" + path,
                    headers={"Authorization": "Bearer " + self.access_token},
                    params=params,
                    json=body,
                    timeout=25,
                )
            except httpx.HTTPError as exc:
                raise DomainError(
                    "google_unavailable" if method == "GET" else "external_uncertain",
                    "Google did not confirm the operation. Review its status before retrying.",
                    502,
                ) from exc
            if (
                response.status_code in {429, 500, 502, 503, 504}
                and method == "GET"
                and attempt < 2
            ):
                time.sleep(2**attempt)
                continue
            if response.status_code >= 500 and method != "GET":
                raise DomainError(
                    "external_uncertain",
                    "Google did not confirm whether the operation completed.",
                    502,
                )
            if response.status_code in {404, 410}:
                raise DomainError(
                    f"google_{response.status_code}",
                    "The Google sync state or resource expired.",
                    409,
                )
            if response.status_code == 401:
                raise DomainError("google_reconnect", "Reconnect Google to continue.", 409)
            if response.status_code == 403:
                raise DomainError(
                    "google_scope",
                    "Google access is missing. Connect the required permission in Settings.",
                    403,
                )
            if response.is_error:
                raise DomainError("google_rejected", "Google rejected the request.", 502)
            return response.json() if response.content else {}
        raise DomainError("google_unavailable", "Google is temporarily unavailable.", 503)


def cursor_for(db: Session, actor: Principal, resource: str) -> SyncCursor:
    row = db.scalar(
        select(SyncCursor).where(
            SyncCursor.user_id == actor.user_id, SyncCursor.resource == resource
        )
    )
    if not row:
        row = SyncCursor(org_id=actor.org_id, user_id=actor.user_id, resource=resource)
        db.add(row)
        db.flush()
    return row


def pages(
    client: GoogleClient, path: str, params: dict[str, Any], key: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records = []
    for _ in range(100):
        response = client.request("GET", path, params=params)
        records.extend(response.get(key, []))
        if not response.get("nextPageToken"):
            return records, response
        params = {**params, "pageToken": response["nextPageToken"]}
    raise DomainError("sync_limit", "Sync exceeds the batch limit. Narrow the import window.", 422)


def message_text(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    text, attachments = [], []
    stack = [payload]
    while stack:
        part = stack.pop()
        stack.extend(part.get("parts", []))
        if part.get("filename"):
            attachments.append(
                {
                    "name": part["filename"],
                    "mime_type": part.get("mimeType"),
                    "size": part.get("body", {}).get("size", 0),
                }
            )
        elif part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            encoded = part["body"]["data"]
            text.append(
                base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode(
                    "utf-8", errors="replace"
                )
            )
    return "\n".join(text)[:100000], attachments


def sync_gmail(db: Session, actor: Principal) -> int:
    client = GoogleClient(db, actor)
    cursor = cursor_for(db, actor, "gmail")
    snapshot = client.request("GET", "gmail/v1/users/me/profile")["historyId"]
    ids: set[str] = set()
    if cursor.cursor:
        try:
            history, _ = pages(
                client,
                "gmail/v1/users/me/history",
                {"startHistoryId": cursor.cursor, "maxResults": 100},
                "history",
            )
            ids = {m["message"]["id"] for h in history for m in h.get("messagesAdded", [])}
        except DomainError as exc:
            if exc.code != "google_404":
                raise
            cursor.cursor = None
    if not cursor.cursor:
        messages, _ = pages(
            client,
            "gmail/v1/users/me/messages",
            {"q": "newer_than:90d -category:promotions -category:social", "maxResults": 100},
            "messages",
        )
        ids = {m["id"] for m in messages}
    count = 0
    for message_id in sorted(ids):
        existing = db.scalar(
            select(Communication).where(
                Communication.external_id == message_id, Communication.owner_id == actor.user_id
            )
        )
        if existing:
            continue
        try:
            data = client.request(
                "GET",
                "gmail/v1/users/me/messages/" + quote(message_id, safe=""),
                params={"format": "full"},
            )
        except DomainError as exc:
            if exc.code == "google_404":
                continue
            raise
        payload = data.get("payload", {})
        headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
        sender_name, sender = parseaddr(headers.get("from", ""))
        recipient_name, recipient = parseaddr(headers.get("to", ""))
        outbound = sender.lower() == (client.integration.email or "").lower()
        email = recipient.lower() if outbound else sender.lower()
        if not email or "@" not in email:
            continue
        contact = db.scalar(select(Contact).where(Contact.email == email))
        body, attachments = message_text(payload)
        if not body:
            body = data.get(
                "snippet", ""
            )  # escaped plain text only; raw HTML never reaches the browser
        if not contact and not any(
            word in (headers.get("subject", "") + " " + body).casefold()
            for word in [
                "property",
                "listing",
                "showing",
                "buy a home",
                "sell my",
                "bedroom",
                "real estate",
            ]
        ):
            continue
        if not contact:
            contact = Contact(
                org_id=actor.org_id,
                email=email,
                name=(recipient_name if outbound else sender_name) or email,
                kind="lead",
                stage="new",
            )
            contact.name = contact.name[:160]
            db.add(contact)
            db.flush()
            from realty.jobs import emit

            emit(db, actor, "LEAD_CREATED", contact.id)
        received = datetime.fromtimestamp(
            int(data.get("internalDate", str(int(time.time() * 1000)))) / 1000, UTC
        ).replace(tzinfo=None)
        message = Communication(
            org_id=actor.org_id,
            owner_id=actor.user_id,
            contact_id=contact.id,
            sender=sender,
            recipient=recipient,
            subject=headers.get("subject", "(No subject)")[:500],
            body=body,
            external_id=message_id,
            thread_id=data.get("threadId"),
            attachments=attachments,
            received_at=received,
            direction="outbound" if outbound else "inbound",
        )
        db.add(message)
        db.flush()
        contact.last_contact_at = max(contact.last_contact_at or received, received)
        db.add(
            Activity(
                org_id=actor.org_id,
                contact_id=contact.id,
                kind="email",
                title=message.subject,
                body=body[:400],
                source_id=message.id,
            )
        )
        db.add(
            Job(
                org_id=actor.org_id,
                kind="analyze_email",
                payload={"message_id": message.id, "user_id": actor.user_id},
                dedupe_key="analyze:" + message.id,
            )
        )
        db.add(
            Job(
                org_id=actor.org_id,
                kind="workflow_event",
                payload={"event": "EMAIL_RECEIVED", "target": contact.id, "user_id": actor.user_id},
                dedupe_key="email-event:" + message.id,
            )
        )
        count += 1
    cursor.cursor = snapshot
    client.integration.last_sync_at, client.integration.last_error = now(), None
    audit(db, actor, "gmail.synced", details={"messages": count})
    return count


def calendar_time(value: dict[str, str]) -> datetime:
    raw = value.get("dateTime") or value.get("date")
    if not raw:
        raise DomainError("calendar_invalid", "Google returned an event without a date.")
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return dt.astimezone(UTC).replace(tzinfo=None) if dt.tzinfo else dt


def sync_calendar(db: Session, actor: Principal, calendar_id: str = "primary") -> int:
    client = GoogleClient(db, actor)
    cursor = cursor_for(db, actor, "calendar:" + calendar_id)
    path = "calendar/v3/calendars/" + quote(calendar_id, safe="") + "/events"
    params: dict[str, Any] = {"maxResults": 250, "singleEvents": "true"}
    if cursor.cursor:
        params["syncToken"] = cursor.cursor
    try:
        events, final = pages(client, path, params, "items")
    except DomainError as exc:
        if exc.code != "google_410":
            raise
        cursor.cursor = None
        events, final = pages(client, path, {"maxResults": 250, "singleEvents": "true"}, "items")
    seen = set()
    for event in events:
        external_id = actor.user_id + ":" + calendar_id + ":" + event["id"]
        seen.add(external_id)
        appointment = db.scalar(select(Appointment).where(Appointment.external_id == external_id))
        if event.get("status") == "cancelled":
            if appointment:
                appointment.status = "cancelled"
            continue
        if not appointment:
            appointment = Appointment(
                org_id=actor.org_id,
                external_id=external_id,
                owner_id=actor.user_id,
                calendar_id=calendar_id,
            )
            db.add(appointment)
        appointment.title = event.get("summary", "Untitled event")[:250]
        appointment.start_at, appointment.end_at = (
            calendar_time(event["start"]),
            calendar_time(event["end"]),
        )
        appointment.location, appointment.status = event.get("location", "")[:250], "confirmed"
        attendees = [a.get("email", "").lower() for a in event.get("attendees", [])]
        contact = (
            db.scalar(select(Contact).where(Contact.email.in_(attendees))) if attendees else None
        )
        appointment.contact_id = contact.id if contact else None
    if not cursor.cursor:
        for old in db.scalars(
            select(Appointment).where(
                Appointment.owner_id == actor.user_id, Appointment.calendar_id == calendar_id
            )
        ).all():
            if old.external_id and old.external_id not in seen:
                old.status = "cancelled"
    cursor.cursor = final.get("nextSyncToken")
    client.integration.last_sync_at = now()
    audit(db, actor, "calendar.synced", details={"events": len(events)})
    return len(events)


def execute_external(db: Session, actor: Principal, action: AIAction) -> dict[str, Any]:
    client = GoogleClient(db, actor)
    if action.kind == "send_email":
        message = EmailMessage()
        message["To"], message["Subject"] = action.payload["to"], action.payload["subject"]
        message["From"] = client.integration.email or ""
        message["Message-ID"] = f"<realty-{action.id}@realty.local>"
        message.set_content(action.payload["body"])
        result = client.request(
            "POST",
            "gmail/v1/users/me/messages/send",
            body={"raw": base64.urlsafe_b64encode(message.as_bytes()).decode()},
        )
        db.add(
            Communication(
                org_id=actor.org_id,
                owner_id=actor.user_id,
                contact_id=action.contact_id,
                direction="outbound",
                sender=client.integration.email or "",
                recipient=action.payload["to"],
                subject=action.payload["subject"],
                body=action.payload["body"],
                external_id=result.get("id"),
                thread_id=result.get("threadId"),
                analyzed=True,
            )
        )
        if action.contact_id:
            require(db, Contact, action.contact_id).last_contact_at = now()
        audit(db, actor, "email.sent", action.id)
        return {"external_id": result.get("id")}
    appointment = None
    event_id = "realty" + action.id.replace("-", "")
    if action.kind != "calendar_create":
        appointment = require(db, Appointment, action.payload["appointment_id"])
        if appointment.owner_id != actor.user_id or not appointment.external_id:
            raise DomainError(
                "calendar_owner", "Only the connected owner can change this Google event.", 403
            )
        event_id = appointment.external_id.rsplit(":", 1)[-1]
    calendar_id = appointment.calendar_id if appointment else "primary"
    path = "calendar/v3/calendars/" + quote(calendar_id or "primary", safe="") + "/events"
    if action.kind == "calendar_delete":
        client.request("DELETE", path + "/" + quote(event_id, safe=""))
        assert appointment is not None
        appointment.status = "cancelled"
        return {"external_id": event_id}
    values = AppointmentInput.model_validate(
        action.payload if action.kind == "calendar_create" else action.payload["event"]
    )
    conflict = db.scalar(
        select(Appointment).where(
            Appointment.status != "cancelled",
            Appointment.start_at < values.end_at,
            Appointment.end_at > values.start_at,
            Appointment.id != (appointment.id if appointment else ""),
        )
    )
    if conflict:
        raise DomainError(
            "calendar_conflict", "This time conflicts with an existing appointment.", 409
        )
    body: dict[str, Any] = {
        "summary": values.title,
        "location": values.location,
        "start": {"dateTime": values.start_at.isoformat() + "Z"},
        "end": {"dateTime": values.end_at.isoformat() + "Z"},
    }
    if action.kind == "calendar_create":
        body["id"] = event_id
        client.request("POST", path, body=body)
        appointment = Appointment(
            org_id=actor.org_id,
            owner_id=actor.user_id,
            calendar_id="primary",
            external_id=actor.user_id + ":primary:" + event_id,
            **values.model_dump(),
        )
        db.add(appointment)
    else:
        client.request("PATCH", path + "/" + quote(event_id, safe=""), body=body)
        assert appointment is not None
        for key, value in values.model_dump().items():
            setattr(appointment, key, value)
    audit(db, actor, action.kind, action.id)
    return {"external_id": event_id}


def disconnect(db: Session, actor: Principal) -> None:
    actor.require("external")
    integration = db.scalar(select(Integration).where(Integration.user_id == actor.user_id))
    if not integration:
        return
    if integration.token_ciphertext:
        tokens = json.loads(cipher().decrypt(integration.token_ciphertext.encode()))
        try:
            response = httpx.post(
                "https://oauth2.googleapis.com/revoke",
                data={"token": tokens.get("refresh_token") or tokens["access_token"]},
                timeout=20,
            )
            if response.status_code not in {200, 400}:
                raise DomainError(
                    "revoke_failed", "Google could not revoke access. Retry disconnect.", 502
                )
        except httpx.HTTPError as exc:
            raise DomainError(
                "revoke_failed", "Google could not revoke access. Retry disconnect.", 502
            ) from exc
    integration.token_ciphertext, integration.status = None, "disconnected"
    db.execute(delete(SyncCursor).where(SyncCursor.user_id == actor.user_id))
    audit(
        db,
        actor,
        "google.disconnected",
        integration.id,
        {"retention": "existing CRM records retained until explicitly deleted"},
    )
