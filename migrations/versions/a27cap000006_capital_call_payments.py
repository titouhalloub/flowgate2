"""add capital call payments: reconciliation against approved calls

Revision ID: a27cap000006
Revises: a27cap000005
Create Date: 2026-09-11

A CapitalCallPayment records money actually received against an APPROVED
capital call. The system never moves money on its own and never absorbs
extra cash: a payment that would exceed the call's remaining balance is
rejected (409), and the paid/partial/unpaid state is always DERIVED from
sum(payments) vs amount_due at read time -- never stored.
"""

import sqlalchemy as sa
from alembic import op


revision = 'a27cap000006'
down_revision = 'a27cap000005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('capital_call_payments',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('capital_call_id', sa.String(length=64), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('currency', sa.String(length=8), nullable=False),
        sa.Column('paid_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reference', sa.String(length=255), nullable=True),
        sa.Column('recorded_by', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['capital_call_id'], ['capital_calls.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_capital_call_payments_call', 'capital_call_payments', ['capital_call_id'], unique=False)
    op.create_index('ix_capital_call_payments_paid_date', 'capital_call_payments', ['paid_date'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_capital_call_payments_paid_date', table_name='capital_call_payments')
    op.drop_index('ix_capital_call_payments_call', table_name='capital_call_payments')
    op.drop_table('capital_call_payments')