# widen webhook_subscriptions.secret for Fernet ciphertext
# Revision ID: a27cap000018
# Revises: a27cap000017
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "a27cap000018"
down_revision: Union[str, None] = "a27cap000017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Fernet output is roughly 3x the plaintext size plus a small header.
    # 128 was fine for plaintext secrets; encrypted values need more room.
    with op.batch_alter_table("webhook_subscriptions") as batch:
        batch.alter_column(
            "secret",
            existing_type=sa.String(length=128),
            type_=sa.String(length=512),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("webhook_subscriptions") as batch:
        batch.alter_column(
            "secret",
            existing_type=sa.String(length=512),
            type_=sa.String(length=128),
            existing_nullable=False,
        )
