"""409A valuations: record-keeping table for issuer FMV / preferred price

Revision ID: a27cap000009
Revises: a27cap000008
Create Date: 2026-09-13
"""

import sqlalchemy as sa
from alembic import op


revision = 'a27cap000009'
down_revision = 'a27cap000008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'valuations',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('issuer_name', sa.String(length=255), nullable=False),
        sa.Column('valuation_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('price_per_share', sa.Float(), nullable=False),
        sa.Column('valuation_type', sa.String(length=32), nullable=False),
        sa.Column('method', sa.String(length=255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_valuations_issuer_date', 'valuations', ['issuer_name', 'valuation_date']
    )
    op.create_index('ix_valuations_type', 'valuations', ['valuation_type'])


def downgrade() -> None:
    op.drop_index('ix_valuations_type', table_name='valuations')
    op.drop_index('ix_valuations_issuer_date', table_name='valuations')
    op.drop_table('valuations')