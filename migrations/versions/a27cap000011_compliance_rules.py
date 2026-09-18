"""add compliance_rules table: Phase 2 compliance-as-configuration

Revision ID: a27cap000011
Revises: a27cap000010
Create Date: 2026-09-18

Additive only. One row = one (predicate, outcome) pair. Rules are
versioned and deactivated, never deleted, so a past evaluation stays
interpretable.
"""

import sqlalchemy as sa
from alembic import op
import sqlalchemy_utils  # noqa: F401 (for JSONType, etc.)

# revision identifiers, used by Alembic.
revision = 'a27cap000011'
down_revision = 'a27cap000010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'compliance_rules',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('package_name', sa.String(length=64), nullable=False),
        sa.Column('rule_name', sa.String(length=64), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('effective_to', sa.Date(), nullable=True),
        sa.Column('label', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('applies_to', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('finding_code', sa.String(length=64), nullable=False),
        sa.Column('severity', sa.Enum('blocking', 'review', 'info', name='rulesseverity', native_enum=False, length=16), nullable=False),
        sa.Column('message', sa.String(length=512), nullable=False),
        sa.Column('condition', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_by', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_compliance_rules_package_active', 'compliance_rules', ['package_name', 'active'], unique=False)
    op.create_index('ix_compliance_rules_effective', 'compliance_rules', ['effective_from'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_compliance_rules_effective', table_name='compliance_rules')
    op.drop_index('ix_compliance_rules_package_active', table_name='compliance_rules')
    op.drop_table('compliance_rules')
    # Drop the enum type if it exists (PostgreSQL)
    op.execute("DROP TYPE IF EXISTS rulesseverity")