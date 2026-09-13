"""add vesting schedules and repurchase fields to cap_table_events

Revision ID: a27cap000008
Revises: a27cap000007
Create Date: 2026-09-13
"""

import sqlalchemy as sa
from alembic import op


revision = 'a27cap000008'
down_revision = 'a27cap000007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('cap_table_events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('vesting_start_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('vesting_period_months', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('cliff_months', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('acceleration_clause', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('is_repurchase', sa.Boolean(), nullable=True, server_default=sa.text('0')))
        batch_op.add_column(sa.Column('repurchase_approver', sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('cap_table_events', schema=None) as batch_op:
        batch_op.drop_column('repurchase_approver')
        batch_op.drop_column('is_repurchase')
        batch_op.drop_column('acceleration_clause')
        batch_op.drop_column('cliff_months')
        batch_op.drop_column('vesting_period_months')
        batch_op.drop_column('vesting_start_date')
