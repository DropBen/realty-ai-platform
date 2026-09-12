from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from realty.db import Base, Record, TenantRecord, now


def contact_fk() -> ForeignKeyConstraint:
    return ForeignKeyConstraint(["org_id", "contact_id"], ["contacts.org_id", "contacts.id"])


class Organization(Record, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(160))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    timezone: Mapped[str] = mapped_column(String(64), default="America/New_York")


class User(Record, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(Text)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    mfa_ciphertext: Mapped[str | None] = mapped_column(Text)
    mfa_pending_ciphertext: Mapped[str | None] = mapped_column(Text)
    mfa_pending_until: Mapped[datetime | None] = mapped_column(DateTime)
    mfa_last_counter: Mapped[int] = mapped_column(Integer, default=-1, server_default="-1")


class Membership(TenantRecord, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("org_id", "user_id"),
        CheckConstraint("role IN ('owner','admin','agent','assistant','viewer')"),
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="agent")


class LoginSession(Record, Base):
    __tablename__ = "sessions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    user_agent: Mapped[str] = mapped_column(String(250), default="", server_default="")
    mfa_verified_at: Mapped[datetime | None] = mapped_column(DateTime)


class AuthToken(Record, Base):
    """Identity-scoped one-use tokens; never serialized through tenant APIs."""

    __tablename__ = "auth_tokens"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(30))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime)


class RecoveryCode(Record, Base):
    __tablename__ = "recovery_codes"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)


class AccountMail(Record, Base):
    __tablename__ = "account_mail"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(40))
    body_ciphertext: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)


class RateBucket(Base):
    __tablename__ = "rate_buckets"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    window: Mapped[int] = mapped_column(Integer)
    count: Mapped[int] = mapped_column(Integer, default=1)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime, default=now, server_default="2000-01-01 00:00:00", index=True
    )


class Contact(TenantRecord, Base):
    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("org_id", "id"),
        UniqueConstraint("org_id", "email"),
        CheckConstraint("kind IN ('lead','buyer','seller','contact')"),
        CheckConstraint("score >= 0 AND score <= 100"),
    )
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(16), default="lead", index=True)
    stage: Mapped[str] = mapped_column(String(40), default="new")
    score: Mapped[int] = mapped_column(Integer, default=0)
    score_reason: Mapped[str] = mapped_column(Text, default="No intent assessment available")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime)
    version: Mapped[int] = mapped_column(Integer, default=1)


class Preference(TenantRecord, Base):
    __tablename__ = "preferences"
    __table_args__ = (
        contact_fk(),
        UniqueConstraint("org_id", "contact_id"),
        CheckConstraint("budget_min IS NULL OR budget_min >= 0"),
        CheckConstraint("budget_max IS NULL OR budget_max >= 0"),
        CheckConstraint("budget_min IS NULL OR budget_max IS NULL OR budget_min <= budget_max"),
    )
    contact_id: Mapped[str] = mapped_column(String(36))
    budget_min: Mapped[int | None] = mapped_column(Integer)
    budget_max: Mapped[int | None] = mapped_column(Integer)
    location: Mapped[str | None] = mapped_column(String(160))
    bedrooms: Mapped[int | None] = mapped_column(Integer)
    bathrooms: Mapped[float | None] = mapped_column(Float)
    property_type: Mapped[str | None] = mapped_column(String(40))
    timeline: Mapped[str | None] = mapped_column(String(160))
    financing: Mapped[str | None] = mapped_column(String(160))
    features: Mapped[list[str]] = mapped_column(JSON, default=list)


class Property(TenantRecord, Base):
    __tablename__ = "properties"
    __table_args__ = (
        UniqueConstraint("org_id", "id"),
        contact_fk(),
        CheckConstraint("price >= 0 AND bedrooms >= 0 AND bathrooms >= 0"),
    )
    contact_id: Mapped[str | None] = mapped_column(String(36))
    address: Mapped[str] = mapped_column(String(250))
    location: Mapped[str] = mapped_column(String(160))
    price: Mapped[int] = mapped_column(Integer)
    bedrooms: Mapped[int] = mapped_column(Integer)
    bathrooms: Mapped[float] = mapped_column(Float)
    sqft: Mapped[int | None] = mapped_column(Integer)
    property_type: Mapped[str] = mapped_column(String(40), default="single_family")
    status: Mapped[str] = mapped_column(String(30), default="active")
    features: Mapped[list[str]] = mapped_column(JSON, default=list)
    images: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(100), default="manual")
    listing_reference: Mapped[str | None] = mapped_column(String(100))


class Deal(TenantRecord, Base):
    __tablename__ = "deals"
    __table_args__ = (
        contact_fk(),
        UniqueConstraint("org_id", "id"),
        ForeignKeyConstraint(["org_id", "property_id"], ["properties.org_id", "properties.id"]),
        CheckConstraint("value >= 0"),
    )
    contact_id: Mapped[str] = mapped_column(String(36))
    property_id: Mapped[str | None] = mapped_column(String(36))
    title: Mapped[str] = mapped_column(String(160))
    stage: Mapped[str] = mapped_column(String(30), default="qualified", index=True)
    value: Mapped[int] = mapped_column(Integer, default=0)
    expected_close: Mapped[datetime | None] = mapped_column(DateTime)
    commission_bps: Mapped[int] = mapped_column(Integer, default=250)


class Transaction(TenantRecord, Base):
    __tablename__ = "transactions"
    __table_args__ = (ForeignKeyConstraint(["org_id", "deal_id"], ["deals.org_id", "deals.id"]),)
    deal_id: Mapped[str] = mapped_column(String(36))
    title: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(30), default="milestone")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    due_at: Mapped[datetime | None] = mapped_column(DateTime)
    amount: Mapped[int | None] = mapped_column(Integer)


class Activity(TenantRecord, Base):
    __tablename__ = "activities"
    __table_args__ = (contact_fk(),)
    contact_id: Mapped[str | None] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(250))
    body: Mapped[str] = mapped_column(Text, default="")
    source_id: Mapped[str | None] = mapped_column(String(100))


class Task(TenantRecord, Base):
    __tablename__ = "tasks"
    __table_args__ = (contact_fk(),)
    contact_id: Mapped[str | None] = mapped_column(String(36), index=True)
    assigned_to: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(250))
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    priority: Mapped[str] = mapped_column(String(20), default="normal")
    due_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    source_id: Mapped[str | None] = mapped_column(String(100))


class Appointment(TenantRecord, Base):
    __tablename__ = "appointments"
    __table_args__ = (
        contact_fk(),
        UniqueConstraint("org_id", "external_id"),
        CheckConstraint("end_at > start_at"),
    )
    contact_id: Mapped[str | None] = mapped_column(String(36))
    title: Mapped[str] = mapped_column(String(250))
    start_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    location: Mapped[str] = mapped_column(String(250), default="")
    status: Mapped[str] = mapped_column(String(30), default="confirmed")
    external_id: Mapped[str | None] = mapped_column(String(1536))
    provider_etag: Mapped[str | None] = mapped_column(String(1024))
    calendar_id: Mapped[str | None] = mapped_column(String(250))
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    all_day: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", server_default="UTC")
    recurrence_id: Mapped[str | None] = mapped_column(String(250))
    original_start: Mapped[str | None] = mapped_column(String(100))


class StorageDeletion(Record, Base):
    """Durable cleanup survives organization deletion; no tenant API exposes it."""

    __tablename__ = "storage_deletions"
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    storage_key: Mapped[str] = mapped_column(String(250), unique=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    error_code: Mapped[str | None] = mapped_column(String(60))


class Communication(TenantRecord, Base):
    __tablename__ = "communications"
    __table_args__ = (
        contact_fk(),
        UniqueConstraint("org_id", "id"),
        UniqueConstraint("org_id", "owner_id", "external_id"),
    )
    contact_id: Mapped[str | None] = mapped_column(String(36), index=True)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    channel: Mapped[str] = mapped_column(String(20), default="email")
    direction: Mapped[str] = mapped_column(String(20), default="inbound")
    sender: Mapped[str] = mapped_column(String(254))
    recipient: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(String(160))
    thread_id: Mapped[str | None] = mapped_column(String(160), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    attachments: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    analyzed: Mapped[bool] = mapped_column(Boolean, default=False)


class Fact(TenantRecord, Base):
    __tablename__ = "facts"
    __table_args__ = (contact_fk(), CheckConstraint("confidence >= 0 AND confidence <= 1"))
    contact_id: Mapped[str] = mapped_column(String(36), index=True)
    field: Mapped[str] = mapped_column(String(60))
    value: Mapped[Any] = mapped_column(JSON)
    source_type: Mapped[str] = mapped_column(String(30))
    source_id: Mapped[str | None] = mapped_column(String(100))
    quote: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(60))
    state: Mapped[str] = mapped_column(String(30), default="extracted")
    verified_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class Commitment(TenantRecord, Base):
    __tablename__ = "commitments"
    __table_args__ = (contact_fk(), Index("ix_commitment_due", "org_id", "status", "due_at"))
    contact_id: Mapped[str] = mapped_column(String(36))
    responsible_user: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(250))
    quote: Mapped[str] = mapped_column(Text, default="", server_default="")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    source_id: Mapped[str] = mapped_column(String(100))
    due_at: Mapped[datetime | None] = mapped_column(DateTime)
    confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(30), default="proposed")


class AIAction(TenantRecord, Base):
    __tablename__ = "ai_actions"
    __table_args__ = (
        contact_fk(),
        UniqueConstraint("org_id", "dedupe_key"),
        Index("ix_action_queue", "org_id", "status", "scheduled_at"),
    )
    contact_id: Mapped[str | None] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(250))
    reason: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20), default="normal")
    confidence: Mapped[float] = mapped_column(Float, default=0)
    source_id: Mapped[str | None] = mapped_column(String(100))
    permission: Mapped[str] = mapped_column(String(30), default="suggested")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_hash: Mapped[str | None] = mapped_column(String(64))
    approval_basis: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(60))
    dedupe_key: Mapped[str | None] = mapped_column(String(250))
    version: Mapped[int] = mapped_column(Integer, default=1)


class Notification(TenantRecord, Base):
    __tablename__ = "notifications"
    title: Mapped[str] = mapped_column(String(250))
    body: Mapped[str] = mapped_column(Text, default="")
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    link: Mapped[str] = mapped_column(String(100), default="/actions")


class Document(TenantRecord, Base):
    __tablename__ = "documents"
    __table_args__ = (contact_fk(),)
    contact_id: Mapped[str | None] = mapped_column(String(36))
    name: Mapped[str] = mapped_column(String(250))
    mime_type: Mapped[str] = mapped_column(String(80))
    storage_key: Mapped[str] = mapped_column(String(250), unique=True)
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    text: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    classification: Mapped[str] = mapped_column(String(60), default="unclassified")
    analysis: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    reviewed_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", name="fk_documents_reviewed_by")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(30), default="stored")


class Integration(TenantRecord, Base):
    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("org_id", "user_id", "provider"),)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    provider: Mapped[str] = mapped_column(String(20), default="google")
    email: Mapped[str | None] = mapped_column(String(254))
    token_ciphertext: Mapped[str | None] = mapped_column(Text)
    scopes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="connected")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(String(100))


class SyncCursor(TenantRecord, Base):
    __tablename__ = "sync_cursors"
    __table_args__ = (UniqueConstraint("org_id", "user_id", "resource"),)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    resource: Mapped[str] = mapped_column(String(250))
    cursor: Mapped[str | None] = mapped_column(Text)


class OAuthState(Record, Base):
    __tablename__ = "oauth_states"
    state_hash: Mapped[str] = mapped_column(String(64), unique=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    verifier: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class Subscription(TenantRecord, Base):
    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("org_id"),)
    customer_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    subscription_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    plan: Mapped[str] = mapped_column(String(30), default="trial")
    status: Mapped[str] = mapped_column(String(30), default="trialing")
    trial_end: Mapped[datetime | None] = mapped_column(DateTime)
    period_end: Mapped[datetime | None] = mapped_column(DateTime)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    last_event_created: Mapped[int] = mapped_column(Integer, default=0)
    checkout_state: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class Usage(TenantRecord, Base):
    __tablename__ = "usage"
    __table_args__ = (Index("ix_usage_month", "org_id", "metric", "created_at"),)
    metric: Mapped[str] = mapped_column(String(40))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    source_id: Mapped[str | None] = mapped_column(String(100))


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    id: Mapped[str] = mapped_column(String(150), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Job(TenantRecord, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("org_id", "dedupe_key"),
        Index("ix_jobs_due", "status", "available_at"),
        Index(
            "uq_active_sync_resource",
            "org_id",
            "resource_key",
            unique=True,
            sqlite_where=text("status IN ('queued','running') AND resource_key IS NOT NULL"),
            postgresql_where=text("status IN ('queued','running') AND resource_key IS NOT NULL"),
        ),
    )
    kind: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    dedupe_key: Mapped[str] = mapped_column(String(250))
    resource_key: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime)
    error_code: Mapped[str | None] = mapped_column(String(60))


class Workflow(TenantRecord, Base):
    __tablename__ = "workflows"
    name: Mapped[str] = mapped_column(String(160))
    trigger: Mapped[str] = mapped_column(String(50))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    condition: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    action: Mapped[str] = mapped_column(String(50))


class Audit(TenantRecord, Base):
    __tablename__ = "audit_events"
    actor_id: Mapped[str | None] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(100), index=True)
    target_id: Mapped[str | None] = mapped_column(String(100))
    result: Mapped[str] = mapped_column(String(30), default="success")
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class WorkerPulse(Base):
    __tablename__ = "worker_pulses"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


class ListingImport(TenantRecord, Base):
    __tablename__ = "listing_imports"
    __table_args__ = (
        UniqueConstraint("org_id", "provider", "reference"),
        ForeignKeyConstraint(["org_id", "property_id"], ["properties.org_id", "properties.id"]),
    )
    provider: Mapped[str] = mapped_column(String(80))
    reference: Mapped[str] = mapped_column(String(100))
    property_id: Mapped[str] = mapped_column(String(36))
    source_updated_at: Mapped[datetime] = mapped_column(DateTime)
    content_hash: Mapped[str] = mapped_column(String(64))
