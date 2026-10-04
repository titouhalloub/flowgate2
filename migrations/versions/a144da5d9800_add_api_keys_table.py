"""add api_keys table

Revision ID: a144da5d9800
Revises: a27cap000018
Create Date: 2026-10-04 13:30:46.831970
"""

import sqlalchemy as sa
from alembic import op

revision = 'a144da5d9800'
down_revision = 'a27cap000018'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Scoped to api_keys only. The autogenerate pass also proposed alterations
    # to unrelated tables because local a27.db was built via create_all()
    # rather than migrations, leaving pre-existing model/schema drift. That
    # drift is tracked in TECH-DEBT.md and is deliberately excluded here so
    # this migration cannot alter any pre-existing table.
    op.create_table(
        'api_keys',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('prefix', sa.String(length=16), nullable=False),
        sa.Column('key_hash', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=False),
        sa.Column('scopes', sa.JSON(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('created_by', sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_api_keys_prefix'), 'api_keys', ['prefix'], unique=True)
    op.create_index(op.f('ix_api_keys_user_id'), 'api_keys', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_api_keys_user_id'), table_name='api_keys')
    op.drop_index(op.f('ix_api_keys_prefix'), table_name='api_keys')
    op.drop_table('api_keys')
