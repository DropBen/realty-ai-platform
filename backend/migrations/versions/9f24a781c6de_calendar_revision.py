"""Bind calendar changes to the provider revision seen by the reviewer."""

import hashlib
import json

import sqlalchemy as sa
from alembic import op

revision = "9f24a781c6de"
down_revision = "6bda8c204a71"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table(
        "appointments", table_args=(sa.CheckConstraint("end_at > start_at"),)
    ) as batch:
        batch.add_column(sa.Column("provider_etag", sa.String(1024), nullable=True))
        batch.alter_column("external_id", existing_type=sa.String(160), type_=sa.String(1536))
    # Historical approvals do not contain a reviewed event revision.
    op.execute(
        "UPDATE ai_actions SET status='pending', approved_by=NULL, approved_hash=NULL, "
        "approval_basis=NULL, version=version+1 "
        "WHERE kind IN ('calendar_update','calendar_delete') AND status='approved'"
    )
    op.add_column("jobs", sa.Column("resource_key", sa.String(64), nullable=True))
    jobs = sa.Table("jobs", sa.MetaData(), autoload_with=op.get_bind())
    active = (
        op.get_bind()
        .execute(
            sa.select(jobs)
            .where(
                jobs.c.kind.in_(["gmail_sync", "calendar_sync"]),
                jobs.c.status.in_(["queued", "running"]),
            )
            .order_by(jobs.c.available_at, jobs.c.id)
        )
        .mappings()
        .all()
    )
    seen: set[tuple[str, str]] = set()
    for job in active:
        payload = job["payload"]
        resource = hashlib.sha256(
            json.dumps(
                [
                    job["kind"],
                    payload.get("user_id"),
                    payload.get("calendar_id", "primary")
                    if job["kind"] == "calendar_sync"
                    else None,
                ]
            ).encode()
        ).hexdigest()
        key = (job["org_id"], resource)
        values = {"resource_key": resource}
        if key in seen:
            values.update(status="done", error_code="coalesced_sync")
        seen.add(key)
        op.get_bind().execute(jobs.update().where(jobs.c.id == job["id"]).values(**values))
    op.create_index(
        "uq_active_sync_resource",
        "jobs",
        ["org_id", "resource_key"],
        unique=True,
        sqlite_where=sa.text("status IN ('queued','running') AND resource_key IS NOT NULL"),
        postgresql_where=sa.text("status IN ('queued','running') AND resource_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_active_sync_resource", table_name="jobs")
    with op.batch_alter_table("jobs") as batch:
        batch.drop_column("resource_key")
    op.execute(
        "UPDATE ai_actions SET status='pending', approved_by=NULL, approved_hash=NULL, "
        "approval_basis=NULL, version=version+1 "
        "WHERE kind IN ('calendar_update','calendar_delete') AND status='approved'"
    )
    # Keep the wider identifier on downgrade; narrowing could truncate real event identities.
    with op.batch_alter_table(
        "appointments", table_args=(sa.CheckConstraint("end_at > start_at"),)
    ) as batch:
        batch.drop_column("provider_etag")
