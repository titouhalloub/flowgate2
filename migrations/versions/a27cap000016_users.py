"""add users table

Revision ID: a27cap000016
Revises: a27cap000015
Create Date: 2026-09-23
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "a27cap000016"
down_revision: Union[str, None] = "a27cap000015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("external_auth_id", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="viewer"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_external_auth_id", "users", ["external_auth_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_external_auth_id", table_name="users")
    op.drop_table("users")
