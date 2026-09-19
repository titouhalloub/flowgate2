"""Phase 2.5g — real JSON Logic conditions for the seeded rule rows.

a27cap000012 seeded the twelve (rule_name, finding_code) pairs with
``condition = {}``. This migration fills each one in with the JSON Logic
expression derived from the branch predicate its callable uses.

The condition's presence is the loader's migration marker: a rule_name
whose rows all carry a non-empty condition runs in row mode and emits
its own finding; a rule_name with any ungated sibling stays in callable
mode. Filling these in therefore flips the DB path from callable mode to
row mode, and the parity tests assert both paths produce identical
findings.

The ``condition`` column is ``sa.JSON()`` -- JSON on Postgres, TEXT on
SQLite. Both accept a JSON-encoded string, so each expression is
``json.dumps``-ed and passed as a bound parameter (no hand-quoting).
"""

import json as _json

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = 'a27cap000013'
down_revision = 'a27cap000012'
branch_labels = None
depends_on = None


# (rule_name, finding_code, condition) -- one entry per seeded row.
# Each condition is the branch predicate from app/compliance.py's
# callable for that finding, expressed in the JSON Logic subset that
# app/json_logic.py evaluates.
CONDITIONS = [
    # --- TRADITIONAL -----------------------------------------------------
    ('kyc_aml_present', 'TRAD_KYC_MISSING',
     {"empty": [{"var": "documents_by_type.kyc"}]}),
    ('interest_rate_sanity', 'TRAD_RATE_MISSING',
     {"empty": [{"var": "instrument.type_specific_data.interest_rate"}]}),
    ('interest_rate_sanity', 'TRAD_RATE_OUT_OF_BAND',
     {"and": [
         {"!": {"empty": [
             {"var": "instrument.type_specific_data.interest_rate"}]}},
         {"!": {"in_range": [
             {"var": "instrument.type_specific_data.interest_rate"},
             0.0, 0.30]}},
     ]}),
    ('mode_info', 'TRAD_MODE_INFO',
     {"==": [1, 1]}),

    # --- ISLAMIC ---------------------------------------------------------
    ('contract_type_declared', 'SHAR_CONTRACT_TYPE_MISSING',
     {"in": [{"var": "instrument.shariah_contract_type"}, [None, "none"]]}),
    ('asset_backing', 'SHAB_ASSET_BACKING_MISSING',
     {"and": [
         {"empty": [{"var": "instrument.underlying_asset_description"}]},
         {"empty": [{"var": "instrument.underlying_asset_id"}]},
     ]}),
    ('asset_backing', 'SHAB_ASSET_PRESENT',
     {"or": [
         {"!": {"empty": [
             {"var": "instrument.underlying_asset_description"}]}},
         {"!": {"empty": [{"var": "instrument.underlying_asset_id"}]}},
     ]}),
    ('no_fixed_interest', 'SHAB_FIXED_INTEREST',
     {"or": [
         {"!": {"empty": [
             {"var": "instrument.type_specific_data.interest_rate"}]}},
         {"==": [
             {"var": "instrument.type_specific_data.fixed_coupon"}, True]},
     ]}),
    ('no_fixed_interest', 'SHAB_NO_FIXED_INTEREST',
     {"!": {"or": [
         {"!": {"empty": [
             {"var": "instrument.type_specific_data.interest_rate"}]}},
         {"==": [
             {"var": "instrument.type_specific_data.fixed_coupon"}, True]},
     ]}}),
    ('fatwa_reference', 'SHAB_FATWA_REFERENCE_MISSING',
     {"empty": [{"var": "documents_by_type.fatwa"}]}),
    ('fatwa_reference', 'SHAB_FATWA_REFERENCE_PRESENT',
     {"!": {"empty": [{"var": "documents_by_type.fatwa"}]}}),
    ('no_speculation', 'SHAB_GHARAR_INDICATOR',
     {"or": [
         {"meaningful": {"var": "instrument.type_specific_data.leverage"}},
         {"meaningful": {"var": "instrument.type_specific_data.margin"}},
         {"meaningful": {"var": "instrument.type_specific_data.derivative"}},
         {"meaningful": {"var": "instrument.type_specific_data.future"}},
     ]}),
]


def upgrade() -> None:
    """Write each row's condition. The rows already exist -- UPDATE, not
    INSERT. ``json.dumps`` keeps the expression as a single bound
    parameter so neither dialect's quoting rules matter."""
    for rule_name, finding_code, condition in CONDITIONS:
        op.execute(
            sa.text(
                "UPDATE compliance_rules SET condition = :cond "
                "WHERE rule_name = :name AND finding_code = :code"
            ).bindparams(
                cond=_json.dumps(condition),
                name=rule_name,
                code=finding_code,
            )
        )


def downgrade() -> None:
    """Return every seeded row to the ungated state a27cap000012 left it
    in, which puts the loader back into callable mode."""
    op.execute(
        sa.text(
            "UPDATE compliance_rules SET condition = '{}' "
            "WHERE created_by = 'migration-a27cap000012'"
        )
    )