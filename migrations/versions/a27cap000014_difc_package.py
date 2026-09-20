"""Phase 2.9 — seed the DIFC compliance rule package.

One row, one rule: DIFC-regulated instruments require KYC/AML on file.
This gives multi-jurisdiction composition (evaluate()'s
``extra_jurisdictions``) a real jurisdiction package to compose with.
The rule reuses the existing JSON Logic operator set ({"empty": [...]})
-- no new operators.

Row shape matches a27cap000012's seed rows exactly. Downgrade removes
every row created by this migration; the rule row is never hard-deleted
by any other path.
"""

import sqlalchemy as sa
from alembic import op
from datetime import date, datetime, timezone

# revision identifiers
revision = 'a27cap000014'
down_revision = 'a27cap000013'
branch_labels = None
depends_on = None

# Local Table matching a27cap000012's column types exactly (migrations
# must not import app.models.orm). The severity enum mirrors the seed
# migration's: name 'rulesseverity', native_enum=False, length=16.
compliance_rules = sa.Table(
    'compliance_rules',
    sa.MetaData(),
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('package_name', sa.String(length=64), nullable=False),
    sa.Column('rule_name', sa.String(length=64), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('effective_from', sa.Date(), nullable=False),
    sa.Column('effective_to', sa.Date(), nullable=True),
    sa.Column('label', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('applies_to', sa.JSON(), nullable=False),
    sa.Column('finding_code', sa.String(length=64), nullable=False),
    sa.Column('severity', sa.Enum('blocking', 'review', 'info',
                                   name='rulesseverity',
                                   native_enum=False,
                                   length=16), nullable=False),
    sa.Column('message', sa.String(length=512), nullable=False),
    sa.Column('condition', sa.JSON(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_by', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
)

DIFC_ROW = {
    'id': 'seed-difc-kyc_required-DIFC_KYC_MISSING',
    'package_name': 'difc',
    'rule_name': 'difc_kyc_required',
    'version': 1,
    'effective_from': date(2026, 1, 1),
    'effective_to': None,
    'label': 'DIFC KYC requirement',
    'description': 'DIFC-regulated instruments require KYC/AML on file.',
    'applies_to': [],
    'finding_code': 'DIFC_KYC_MISSING',
    'severity': 'blocking',
    'message': 'DIFC KYC/AML document missing.',
    'condition': {'empty': [{'var': 'documents_by_type.kyc'}]},
    'active': True,
    'created_by': 'migration-a27cap000014',
    'created_at': datetime.now(timezone.utc),
}


def upgrade() -> None:
    # Idempotent: skip if this migration already seeded its row.
    connection = op.get_bind()
    stmt = sa.sql.select(sa.literal(True)).where(
        compliance_rules.c.created_by == 'migration-a27cap000014'
    ).limit(1)
    if connection.execute(stmt).scalar() is not None:
        return
    op.bulk_insert(compliance_rules, [DIFC_ROW])


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM compliance_rules "
            "WHERE created_by = 'migration-a27cap000014'"
        )
    )
