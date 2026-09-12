"""add transfer rules + evaluations: Phase D governance gate

Revision ID: a27cap000007
Revises: a27cap000006
Create Date: 2026-09-11

Additive only (same convention as 3-6). transfer_rules are prepared
governance evaluated against proposed TRANSFER events in the event-write
path; transfer_evaluations are the immutable per-decision audit rows --
ALLOWED transfers get one too, so every gate decision is answerable later.
Nothing here changes the event-sourcing replay.
"""

import sqlalchemy as sa
from alembic import op


revision = 'a27cap000007'
down_revision = 'a27cap000006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('transfer_rules',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('issuer_name', sa.String(length=255), nullable=False),
        sa.Column('rule_type', sa.String(length=32), nullable=False),
        sa.Column('condition', sa.JSON(), nullable=True),
        sa.Column('gate', sa.String(length=16), nullable=False),
        sa.Column('approver', sa.String(length=255), nullable=False),
        sa.Column('escalation_role', sa.String(length=255), nullable=True),
        sa.Column('escalation_after_days', sa.Integer(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=True),
        sa.Column('created_by', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_transfer_rules_issuer_name', 'transfer_rules', ['issuer_name'], unique=False)
    op.create_index('ix_transfer_rules_active', 'transfer_rules', ['active'], unique=False)

    op.create_table('transfer_evaluations',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('security_id', sa.String(length=64), nullable=False),
        sa.Column('from_holder_id', sa.String(length=64), nullable=False),
        sa.Column('holder_id', sa.String(length=64), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('price_per_share', sa.Float(), nullable=True),
        sa.Column('effective_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('rules_evaluated', sa.JSON(), nullable=True),
        sa.Column('outcome', sa.String(length=24), nullable=True),
        sa.Column('blocking_rule_id', sa.String(length=64), nullable=True),
        sa.Column('reviewer', sa.String(length=64), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['security_id'], ['securities.id'], ),
        sa.ForeignKeyConstraint(['from_holder_id'], ['investors.id'], ),
        sa.ForeignKeyConstraint(['holder_id'], ['investors.id'], ),
        sa.ForeignKeyConstraint(['blocking_rule_id'], ['transfer_rules.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_transfer_evaluations_security_id', 'transfer_evaluations', ['security_id'], unique=False)
    op.create_index('ix_transfer_evaluations_outcome', 'transfer_evaluations', ['outcome'], unique=False)
    op.create_index('ix_transfer_evaluations_created_at', 'transfer_evaluations', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_transfer_evaluations_created_at', table_name='transfer_evaluations')
    op.drop_index('ix_transfer_evaluations_outcome', table_name='transfer_evaluations')
    op.drop_index('ix_transfer_evaluations_security_id', table_name='transfer_evaluations')
    op.drop_table('transfer_evaluations')
    op.drop_index('ix_transfer_rules_active', table_name='transfer_rules')
    op.drop_index('ix_transfer_rules_issuer_name', table_name='transfer_rules')
    op.drop_table('transfer_rules')