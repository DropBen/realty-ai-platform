from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, Field, model_validator


def utc_naive(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    return dt.astimezone(UTC).replace(tzinfo=None) if dt.tzinfo else dt


Date = Annotated[datetime, BeforeValidator(utc_naive)]
Name = Annotated[str, Field(min_length=1, max_length=160)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Register(Input):
    name: Name
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    organization: Name


class Login(Input):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ContactInput(Input):
    name: Name
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=40)
    kind: Literal["lead", "buyer", "seller", "contact"] = "lead"
    stage: Literal["new", "nurturing", "qualified", "active", "closed"] = "new"
    archived: bool = False


class PreferenceInput(Input):
    budget_min: int | None = Field(None, ge=0, le=2_000_000_000)
    budget_max: int | None = Field(None, ge=0, le=2_000_000_000)
    location: str | None = Field(None, max_length=160)
    bedrooms: int | None = Field(None, ge=0, le=100)
    bathrooms: float | None = Field(None, ge=0, le=100)
    property_type: str | None = Field(None, max_length=40)
    timeline: str | None = Field(None, max_length=160)
    financing: str | None = Field(None, max_length=160)
    features: list[Annotated[str, Field(max_length=60)]] = Field(
        default_factory=list, max_length=30
    )

    @model_validator(mode="after")
    def budget_order(self) -> "PreferenceInput":
        if (
            self.budget_min is not None
            and self.budget_max is not None
            and self.budget_min > self.budget_max
        ):
            raise ValueError("Minimum budget cannot exceed maximum budget")
        return self


class PropertyInput(Input):
    address: str = Field(min_length=1, max_length=250)
    location: Name
    price: int = Field(ge=0, le=2_000_000_000)
    bedrooms: int = Field(ge=0, le=100)
    bathrooms: float = Field(ge=0, le=100)
    sqft: int | None = Field(None, ge=1, le=10_000_000)
    property_type: Literal["single_family", "condo", "townhouse", "multi_family", "land"] = (
        "single_family"
    )
    status: Literal["active", "pending", "sold", "withdrawn"] = "active"
    features: list[Annotated[str, Field(max_length=60)]] = Field(
        default_factory=list, max_length=30
    )
    contact_id: str | None = None
    source: str = Field("manual", max_length=100)
    listing_reference: str | None = Field(None, max_length=100)


class DealInput(Input):
    title: Name
    contact_id: str
    property_id: str | None = None
    stage: Literal["qualified", "showing", "offer", "under_contract", "closed", "lost"] = (
        "qualified"
    )
    value: int = Field(0, ge=0, le=2_000_000_000)
    expected_close: Date | None = None
    commission_bps: int = Field(250, ge=0, le=10000)


class TaskInput(Input):
    title: str = Field(min_length=1, max_length=250)
    contact_id: str | None = None
    assigned_to: str | None = None
    priority: Literal["normal", "high", "urgent"] = "normal"
    status: Literal["open", "done", "cancelled"] = "open"
    due_at: Date | None = None


class AppointmentInput(Input):
    title: str = Field(min_length=1, max_length=250)
    contact_id: str | None = None
    start_at: Date
    end_at: Date
    location: str = Field("", max_length=250)

    @model_validator(mode="after")
    def interval(self) -> "AppointmentInput":
        if self.end_at <= self.start_at:
            raise ValueError("Appointment must end after it starts")
        return self


class NoteInput(Input):
    title: str = Field(min_length=1, max_length=250)
    body: str = Field("", max_length=20000)
    kind: Literal["note", "call", "showing", "feedback", "offer", "price_change"] = "note"


class ActionInput(Input):
    kind: Literal[
        "crm_update",
        "create_task",
        "send_email",
        "calendar_create",
        "calendar_update",
        "calendar_delete",
    ]
    title: str = Field(min_length=1, max_length=250)
    reason: str = Field(min_length=1, max_length=4000)
    contact_id: str | None = None
    priority: Literal["normal", "high", "urgent"] = "normal"
    payload: dict[str, Any]
    source_id: str | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)


class Decision(Input):
    decision: Literal["approve", "reject", "snooze", "undo", "edit", "retry"]
    version: int = Field(ge=1)
    payload: dict[str, Any] | None = None
    scheduled_at: Date | None = None


class CRMUpdate(Input):
    contact_id: str
    changes: PreferenceInput


class EmailPayload(Input):
    to: EmailStr
    subject: str = Field(min_length=1, max_length=250, pattern=r"^[^\r\n]+$")
    body: str = Field(min_length=1, max_length=20000)


class CalendarChange(Input):
    appointment_id: str
    event: AppointmentInput | None = None


class Query(Input):
    question: str = Field(min_length=1, max_length=2000)


class WorkflowInput(Input):
    name: Name
    trigger: Literal["LEAD_CREATED", "PROPERTY_CREATED", "FOLLOW_UP_REQUIRED", "EMAIL_RECEIVED"]
    action: Literal["notify", "recommend_followup", "match_properties"]
    condition: dict[Literal["min_score"], Annotated[int, Field(ge=0, le=100)]] = Field(
        default_factory=dict
    )
    enabled: bool = True

    @model_validator(mode="after")
    def compatible_workflow(self) -> "WorkflowInput":
        if self.action == "match_properties" and self.trigger != "PROPERTY_CREATED":
            raise ValueError("Property matching requires the property-created trigger")
        if self.trigger == "PROPERTY_CREATED" and self.action == "recommend_followup":
            raise ValueError("Choose property matching or a notification for new properties")
        return self


class TransactionInput(Input):
    deal_id: str
    title: Name
    kind: Literal["milestone", "offer", "inspection", "closing", "deposit"] = "milestone"
    status: Literal["pending", "complete", "cancelled"] = "pending"
    due_at: Date | None = None
    amount: int | None = Field(None, ge=0, le=2_000_000_000)
