"""Phase 2.3 — seeded compliance rule catalogue.

One migration inserts the twelve (rule_name, finding_code) pairs that
the current app/compliance.py rules can emit, split so each row carries
exactly one finding. Multiple rows can share a rule_name; the loader
dedups by rule_name before callable lookup so each callable runs
exactly once per evaluation.
"""

import sqlalchemy as sa
from alembic import op
from datetime import date, datetime, timezone

# revision identifiers
revision = 'a27cap000012'
down_revision = 'a27cap000011'
branch_labels = None
depends_on = None

# Local Table matching the migration's own column types. Migrations must
# not import app.models.orm (which would pin them to the current ORM
# schema and to rule-callable references).
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


# (rule_name, finding_code, severity_str, message, label)
# Each finding_code/severity is taken verbatim from app/compliance.py.
SEED = [
    # TRADITIONAL
    ('kyc_aml_present',     'TRAD_KYC_MISSING',            'blocking',
     'No KYC/AML document attached to the instrument.',
     'KYC/AML presence check'),
    ('interest_rate_sanity','TRAD_RATE_MISSING',           'review',
     'No interest_rate on record; cannot apply sanity bounds.',
     'Interest rate presence'),
    ('interest_rate_sanity','TRAD_RATE_OUT_OF_BAND',       'blocking',
     'Interest rate outside acceptable band [0, 0.30].',
     'Interest rate bounds'),
    ('mode_info',            'TRAD_MODE_INFO',              'info',
     'Instrument evaluated under traditional track.',
     'Compliance mode info'),
    # ISLAMIC
    ('contract_type_declared','SHAR_CONTRACT_TYPE_MISSING','blocking',
     'Islamic instrument is missing a declared Shariah contract type.',
     'Shariah contract type declared'),
    ('asset_backing',        'SHAB_ASSET_BACKING_MISSING',  'blocking',
     'Islamic instrument has no underlying asset description or ID.',
     'Asset backing present'),
    ('asset_backing',        'SHAB_ASSET_PRESENT',          'info',
     'Underlying asset is declared for the Islamic instrument.',
     'Asset backing present'),
    ('no_fixed_interest',    'SHAB_FIXED_INTEREST',         'blocking',
     'Fixed interest / fixed coupon detected on the Islamic track.',
     'No fixed interest'),
    ('no_fixed_interest',    'SHAB_NO_FIXED_INTEREST',      'info',
     'No fixed-interest indicators found in type_specific_data.',
     'No fixed interest'),
    ('fatwa_reference',      'SHAB_FATWA_REFERENCE_MISSING','blocking',
     'No FATWA document attached; cannot route for scholar review.',
     'Fatwa reference present'),
    ('fatwa_reference',      'SHAB_FATWA_REFERENCE_PRESENT','info',
     'Fatwa document(s) attached for the scholar.',
     'Fatwa reference present'),
    ('no_speculation',       'SHAB_GHARAR_INDICATOR',       'blocking',
     'Instrument exhibits potential speculative indicators: {hits}.',
     'No speculation (gharar)'),
]


def upgrade() -> None:
    # Idempotent: skip if already seeded. Check table presence first so a
    # downgrade-to-11 (which drops the table) can re-upgrade cleanly.
    insp = sa.inspect(op.get_bind())
    if 'compliance_rules' not in insp.get_table_names():
        # Table missing. a27cap000011 created it -- a downgrade to 000011
        # dropped it, in which case recreate it here and seed.
        _recreate_table()
    if _already_seeded():
        return

    rows = []
    for rule_name, finding_code, severity, message, label in SEED:
        rows.append({
            'id': f'seed-{rule_name}-{finding_code}',
            'package_name': _package_for(rule_name),
            'rule_name': rule_name,
            'version': 1,
            'effective_from': date(2026, 1, 1),
            'effective_to': None,
            'label': label,
            'description': None,
            'applies_to': [],
            'finding_code': finding_code,
            'severity': severity,
            'message': message,
            'condition': {},
            'active': True,
            'created_by': 'migration-a27cap000012',
            'created_at': datetime.now(timezone.utc),
        })

    op.bulk_insert(compliance_rules, rows)


def downgrade() -> None:
    # Remove every row this migration created.
    connection = op.get_bind()
    stmt = compliance_rules.delete().where(
        compliance_rules.c.created_by == 'migration-a27cap000012'
    )
    connection.execute(stmt)


def _already_seeded() -> bool:
    connection = op.get_bind()
    stmt = sa.sql.select(sa.literal(True)).where(
        compliance_rules.c.created_by == 'migration-a27cap000012'
    ).limit(1)
    return connection.execute(stmt).scalar() is not None


def _recreate_table() -> None:
    """Recreate compliance_rules with the same columns a27cap000011 used.

    a27cap000011's downgrade drops the whole table (including its
    ``DROP TYPE`` of the Postgres enum). If someone downgrades to
    a27cap000011 and re-upgrades, this migration must not assume the
    table still exists, so it recreates it before seeding.
    """
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
        sa.Column('severity', sa.Enum('blocking', 'review', 'info',
                                       name='rulesseverity',
                                       native_enum=False,
                                       length=16), nullable=False),
        sa.Column('message', sa.String(length=512), nullable=False),
        sa.Column('condition', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_by', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_compliance_rules_package_active',
                    'compliance_rules', ['package_name', 'active'], unique=False)
    op.create_index('ix_compliance_rules_effective',
                    'compliance_rules', ['effective_from'], unique=False)


def _package_for(rule_name: str) -> str:
    """Map each rule_name to the correct package. Determined by the
    rule sets in app/compliance.py: TRADITIONAL_RULES vs ISLAMIC_RULES.
    """
    _TRADITIONAL = {
        'kyc_aml_present',
        'interest_rate_sanity',
        'mode_info',
    }
    return 'traditional' if rule_name in _TRADITIONAL else 'islamic'
