"""Bind OAuth to its workspace and CRM approvals to reviewed values."""

import sqlalchemy as sa
from alembic import op

revision = "6bda8c204a71"
down_revision = "2375a43c78e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ten-minute requests cannot safely be attributed after a session has switched.
    op.execute("DELETE FROM oauth_states")
    with op.batch_alter_table("oauth_states") as batch:
        batch.add_column(sa.Column("org_id", sa.String(36), nullable=False))
        batch.create_foreign_key(
            "fk_oauth_states_org_id", "organizations", ["org_id"], ["id"], ondelete="CASCADE"
        )
    with op.batch_alter_table("ai_actions") as batch:
        batch.add_column(sa.Column("approval_basis", sa.JSON(), nullable=True))
    with op.batch_alter_table("subscriptions") as batch:
        batch.add_column(sa.Column("checkout_state", sa.JSON(), nullable=True))
    # Never infer the basis of a historical approval. New review is mandatory.
    op.execute(
        "UPDATE ai_actions SET status='pending', approved_by=NULL, approved_hash=NULL, "
        "version=version+1 WHERE kind='crm_update' AND status='approved'"
    )


def downgrade() -> None:
    op.execute("DELETE FROM oauth_states")
    # The old binary does not understand the new approval digest.
    op.execute(
        "UPDATE ai_actions SET status='pending', approved_by=NULL, approved_hash=NULL, "
        "version=version+1 WHERE kind='crm_update' AND status='approved'"
    )
    with op.batch_alter_table("subscriptions") as batch:
        batch.drop_column("checkout_state")
    with op.batch_alter_table("ai_actions") as batch:
        batch.drop_column("approval_basis")
    with op.batch_alter_table("oauth_states") as batch:
        batch.drop_constraint("fk_oauth_states_org_id", type_="foreignkey")
        batch.drop_column("org_id")
