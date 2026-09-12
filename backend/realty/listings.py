"""Normalized, user-reviewed listing imports. Live MLS access is a separate provider port."""

import csv
import hashlib
import io
import json
from datetime import timedelta
from typing import Any, Protocol

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from pydantic import Field, ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from realty.db import get_db, now
from realty.errors import DomainError
from realty.models import ListingImport, Organization, Property
from realty.repository import public, require, validate_refs
from realty.schemas import Date, Input, PropertyInput
from realty.security import Principal, audit, principal

router = APIRouter(tags=["Listing imports"])


class NormalizedListing(Input):
    reference: str = Field(min_length=1, max_length=100)
    updated_at: Date
    property: PropertyInput


class ListingBatch(Input):
    provider: str = Field(min_length=2, max_length=80, pattern=r"^[a-z][a-z0-9_]+$")
    items: list[NormalizedListing] = Field(min_length=1, max_length=100)


class ListingProvider(Protocol):
    """Adapter must enforce its feed license and map provider data before ingestion."""

    def changes(self, cursor: str | None) -> tuple[list[NormalizedListing], str | None]: ...


def content_hash(values: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def review_batch(
    db: Session, actor: Principal, batch: ListingBatch, commit: bool
) -> list[dict[str, Any]]:
    actor.require("approve")
    if len({item.reference for item in batch.items}) != len(batch.items):
        raise DomainError(
            "duplicate_listing", "Each import reference must occur only once per batch.", 422
        )
    if commit:
        # Serialize imports for one organization, including first-seen references.
        if db.get_bind().dialect.name == "sqlite":
            db.execute(
                update(Organization)
                .where(Organization.id == actor.org_id)
                .values(name=Organization.name, updated_at=Organization.updated_at)
            )
        db.scalar(select(Organization).where(Organization.id == actor.org_id).with_for_update())
    result = []
    for item in batch.items:
        if item.updated_at > now() + timedelta(minutes=5):
            raise DomainError(
                "invalid_listing_time", "A listing revision cannot be in the future.", 422
            )
        values = {
            **item.property.model_dump(),
            "source": batch.provider,
            "listing_reference": item.reference,
        }
        validate_refs(db, values)
        digest = content_hash(values)
        mapping = db.scalar(
            select(ListingImport).where(
                ListingImport.provider == batch.provider, ListingImport.reference == item.reference
            )
        )
        prop = require(db, Property, mapping.property_id) if mapping else None
        state = "create"
        if mapping:
            if item.updated_at < mapping.source_updated_at:
                state = "stale"
            elif digest == mapping.content_hash:
                state = "unchanged"
            elif item.updated_at == mapping.source_updated_at:
                raise DomainError(
                    "listing_revision_conflict",
                    "The same listing revision contains different values.",
                    409,
                )
            else:
                state = "update"
            # Preserve human edits until the user resolves them explicitly in CRM.
            if state == "update" and prop:
                current = {key: getattr(prop, key) for key in values}
                if content_hash(current) != mapping.content_hash:
                    raise DomainError(
                        "listing_manual_conflict",
                        "This listing has manual edits. Review the existing record before importing a replacement.",
                        409,
                    )
        if commit and state in {"create", "update"}:
            if not prop:
                prop = Property(org_id=actor.org_id, **values)
                db.add(prop)
                db.flush()
                mapping = ListingImport(
                    org_id=actor.org_id,
                    provider=batch.provider,
                    reference=item.reference,
                    property_id=prop.id,
                    source_updated_at=item.updated_at,
                    content_hash=digest,
                )
                db.add(mapping)
                from realty.jobs import emit

                emit(db, actor, "PROPERTY_CREATED", prop.id)
            else:
                for key, value in values.items():
                    setattr(prop, key, value)
                assert mapping is not None
                mapping.source_updated_at, mapping.content_hash = item.updated_at, digest
            audit(
                db,
                actor,
                "listing." + state,
                prop.id,
                {"provider": batch.provider, "reference": item.reference},
            )
        elif (
            commit
            and mapping
            and state == "unchanged"
            and item.updated_at > mapping.source_updated_at
        ):
            mapping.source_updated_at = item.updated_at
        result.append(
            {
                "reference": item.reference,
                "status": state,
                "address": values["address"],
                "property": public(prop) if prop else None,
            }
        )
    return result


@router.post("/listings/preview")
def preview(
    batch: ListingBatch,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    return {
        "items": review_batch(db, actor, batch, False),
        "source": "user_supplied",
        "live_mls": False,
    }


@router.post("/listings/import")
def import_listings(
    batch: ListingBatch,
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    return {
        "items": review_batch(db, actor, batch, True),
        "source": "user_supplied",
        "live_mls": False,
    }


@router.get("/listings/template")
def template(actor: Principal = Depends(principal)) -> Response:
    content = "reference,updated_at,address,location,price,bedrooms,bathrooms,features\nexample-001,2026-01-01T00:00:00Z,12 Example Lane,Sample City,550000,3,2,garage;garden\n"
    return Response(
        content,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="listing-import-template.csv"'},
    )


@router.post("/listings/preview-file")
async def preview_file(
    file: UploadFile = File(...),
    provider: str = Form("manual_upload"),
    actor: Principal = Depends(principal),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, Any]:
    actor.require("approve")
    try:
        raw = await file.read(1_000_001)
    finally:
        await file.close()
    if len(raw) > 1_000_000:
        raise DomainError(
            "import_size", "Listing imports are limited to 1 MB and 100 records.", 413
        )
    try:
        decoded = raw.decode("utf-8-sig")
        if (file.filename or "").lower().endswith(".json"):
            batch = ListingBatch.model_validate(json.loads(decoded))
        elif (file.filename or "").lower().endswith(".csv"):
            items = []
            for row in csv.DictReader(io.StringIO(decoded), strict=True):
                reference, updated = row.pop("reference"), row.pop("updated_at")
                row["features"] = [
                    value.strip() for value in row.get("features", "").split(";") if value.strip()
                ]
                items.append({"reference": reference, "updated_at": updated, "property": row})
                if len(items) > 100:
                    raise ValueError("Too many records")
            batch = ListingBatch.model_validate({"provider": provider, "items": items})
        else:
            raise ValueError("Unsupported file")
    except (ValueError, TypeError, KeyError, csv.Error, ValidationError, AttributeError) as exc:
        raise DomainError(
            "invalid_listing_file",
            "Use a UTF-8 CSV matching the template or a valid normalized JSON batch, with at most 100 records.",
            422,
        ) from exc
    return {
        "items": review_batch(db, actor, batch, False),
        "batch": batch.model_dump(mode="json"),
        "live_mls": False,
    }
