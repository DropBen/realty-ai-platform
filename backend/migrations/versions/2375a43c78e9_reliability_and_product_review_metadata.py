"""reliability and product review metadata"""

import sqlalchemy as sa
from alembic import op

revision = "2375a43c78e9"
down_revision = "35b63b33b85a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "storage_deletions",
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("storage_key", sa.String(length=250), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(), nullable=False),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    with op.batch_alter_table("storage_deletions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_storage_deletions_available_at"), ["available_at"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_storage_deletions_org_id"), ["org_id"], unique=False)

    op.create_table(
        "worker_pulses",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("last_seen", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("worker_pulses", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_worker_pulses_last_seen"), ["last_seen"], unique=False)

    op.create_table(
        "listing_imports",
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id", "property_id"],
            ["properties.org_id", "properties.id"],
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "provider", "reference"),
    )
    with op.batch_alter_table("listing_imports", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_listing_imports_org_id"), ["org_id"], unique=False)

    with op.batch_alter_table("appointments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("all_day", sa.Boolean(), server_default="0", nullable=False))
        batch_op.add_column(
            sa.Column("timezone", sa.String(length=64), server_default="UTC", nullable=False)
        )
        batch_op.add_column(sa.Column("recurrence_id", sa.String(length=250), nullable=True))
        batch_op.add_column(sa.Column("original_start", sa.String(length=100), nullable=True))

    with op.batch_alter_table("commitments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("quote", sa.Text(), server_default="", nullable=False))
        batch_op.add_column(sa.Column("version", sa.Integer(), server_default="1", nullable=False))
        batch_op.create_index("ix_commitment_due", ["org_id", "status", "due_at"], unique=False)

    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.add_column(sa.Column("analysis", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("reviewed_by", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(), nullable=True))
        batch_op.create_foreign_key("fk_documents_reviewed_by", "users", ["reviewed_by"], ["id"])

    with op.batch_alter_table("rate_buckets", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "expires_at", sa.DateTime(), server_default="2000-01-01 00:00:00", nullable=False
            )
        )
        batch_op.create_index(
            batch_op.f("ix_rate_buckets_expires_at"), ["expires_at"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("rate_buckets", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_rate_buckets_expires_at"))
        batch_op.drop_column("expires_at")

    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.drop_constraint("fk_documents_reviewed_by", type_="foreignkey")
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("reviewed_by")
        batch_op.drop_column("analysis")

    with op.batch_alter_table("commitments", schema=None) as batch_op:
        batch_op.drop_index("ix_commitment_due")
        batch_op.drop_column("version")
        batch_op.drop_column("quote")

    with op.batch_alter_table("appointments", schema=None) as batch_op:
        batch_op.drop_column("original_start")
        batch_op.drop_column("recurrence_id")
        batch_op.drop_column("timezone")
        batch_op.drop_column("all_day")

    with op.batch_alter_table("listing_imports", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_listing_imports_org_id"))

    op.drop_table("listing_imports")
    with op.batch_alter_table("worker_pulses", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_worker_pulses_last_seen"))

    op.drop_table("worker_pulses")
    with op.batch_alter_table("storage_deletions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_storage_deletions_org_id"))
        batch_op.drop_index(batch_op.f("ix_storage_deletions_available_at"))

    op.drop_table("storage_deletions")
