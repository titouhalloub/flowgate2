"""Convertibles and priced rounds: off-cap-table SAFEs, conversion on priced round

Revision ID: a27cap000010
Revises: a27cap000009
Create Date: 2026-09-14
"""

import sqlalchemy as sa
from alembic import op

revision = 'a27cap000010'
down_revision = 'a27cap000009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite doesn't support ALTER TABLE ... ADD COLUMN with FK in batch mode,
    # but we can add the columns first, then create the tables.
    # For SQLite, use batch mode for adding columns to existing table.
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'

    # Create convertibles table
    op.create_table(
        'convertibles',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('issuer_name', sa.String(length=255), nullable=False),
        sa.Column('investor_name', sa.String(length=255), nullable=False),
        sa.Column('document_id', sa.String(length=64), nullable=True),
        sa.Column('purchase_amount', sa.Float(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='USD'),
        sa.Column('instrument_kind', sa.String(length=32), nullable=False),
        sa.Column('valuation_cap', sa.Float(), nullable=False),
        sa.Column('discount_rate', sa.Float(), nullable=True),
        sa.Column('pro_rata_rights', sa.Boolean(), nullable=True),
        sa.Column('mfn_clause', sa.Boolean(), nullable=True),
        sa.Column('conversion_trigger', sa.Text(), nullable=True),
        sa.Column('issued_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='outstanding'),
        sa.Column('converted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('conversion_event_id', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_convertibles_issuer', 'convertibles', ['issuer_name'])
    op.create_index('ix_convertibles_status', 'convertibles', ['status'])

    # Create priced_rounds table
    op.create_table(
        'priced_rounds',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('issuer_name', sa.String(length=255), nullable=False),
        sa.Column('round_name', sa.String(length=64), nullable=False),
        sa.Column('price_per_share', sa.Float(), nullable=False),
        sa.Column('round_shares', sa.Integer(), nullable=False),
        sa.Column('post_money_shares', sa.Integer(), nullable=False),
        sa.Column('effective_date', sa.Date(), nullable=False),
        sa.Column('reviewer', sa.String(length=255), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('client_request_id', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_priced_rounds_issuer', 'priced_rounds', ['issuer_name'])
    op.create_unique_constraint('uq_priced_rounds_crid', 'priced_rounds', ['client_request_id'])

    # Add FK columns to cap_table_events
    if is_sqlite:
        with op.batch_alter_table('cap_table_events') as batch_op:
            batch_op.add_column(sa.Column('related_convertible_id', sa.String(length=64), nullable=True))
            batch_op.add_column(sa.Column('related_round_id', sa.String(length=64), nullable=True))
    else:
        op.add_column('cap_table_events', sa.Column('related_convertible_id', sa.String(length=64), nullable=True))
        op.add_column('cap_table_events', sa.Column('related_round_id', sa.String(length=64), nullable=True))

    # Add index on related_round_id for audit trail lookups
    op.create_index('ix_captable_related_round', 'cap_table_events', ['related_round_id'])


def downgrade() -> None:
    op.drop_index('ix_captable_related_round', table_name='cap_table_events')

    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'

    if is_sqlite:
        with op.batch_alter_table('cap_table_events') as batch_op:
            batch_op.drop_column('related_round_id')
            batch_op.drop_column('related_convertible_id')
    else:
        op.drop_column('cap_table_events', 'related_round_id')
        op.drop_column('cap_table_events', 'related_convertible_id')

    op.drop_constraint('uq_priced_rounds_crid', 'priced_rounds', type_='unique')
    op.drop_index('ix_priced_rounds_issuer', table_name='priced_rounds')
    op.drop_table('priced_rounds')

    op.drop_index('ix_convertibles_status', table_name='convertibles')
    op.drop_index('ix_convertibles_issuer', table_name='convertibles')
    op.drop_table('convertibles')