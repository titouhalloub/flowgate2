# add webhook_subscriptions and webhook_deliveries
# Revision ID: a27cap000017
# Revises: a27cap000016
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "a27cap000017"
down_revision: Union[str, None] = "a27cap000016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webhook_subscriptions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("secret", sa.String(length=128), nullable=False),
        sa.Column("events", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_webhook_subscriptions_active", "webhook_subscriptions", ["active"])

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("subscription_id", sa.String(length=64), sa.ForeignKey("webhook_subscriptions.id"), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_webhook_deliveries_subscription",
        "webhook_deliveries",
        ["subscription_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_webhook_deliveries_subscription", table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")
    op.drop_index("ix_webhook_subscriptions_active", table_name="webhook_subscriptions")
    op.drop_table("webhook_subscriptions")
