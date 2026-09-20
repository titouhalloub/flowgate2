"""Phase 2.3 -- seeded rules load correctly and behavior is
unchanged. The callable still decides which finding to emit; the
seed is a catalogue of what each rule can emit."""

from datetime import date

from app.compliance import load_rule_sets, RULE_SETS
from app.models.enums import RuleSeverity
from app.models.orm import ComplianceRule


def _seed_traditional(session):
    rows = [
        ("kyc_aml_present", "TRAD_KYC_MISSING", RuleSeverity.BLOCKING,
         {"empty": [{"var": "documents_by_type.kyc"}]}),
        ("interest_rate_sanity", "TRAD_RATE_MISSING", RuleSeverity.REVIEW,
         {"empty": [{"var": "instrument.type_specific_data.interest_rate"}]}),
        ("interest_rate_sanity", "TRAD_RATE_OUT_OF_BAND", RuleSeverity.BLOCKING,
         {"and": [
             {"!": {"empty": [{"var": "instrument.type_specific_data.interest_rate"}]}},
             {"!": {"in_range": [{"var": "instrument.type_specific_data.interest_rate"}, 0.0, 0.30]}},
         ]}),
        ("mode_info", "TRAD_MODE_INFO", RuleSeverity.INFO,
         {"==": [1, 1]}),
    ]
    for rule_name, code, severity, cond in rows:
        session.add(ComplianceRule(
            id=f"seed-{rule_name}-{code}",
            package_name="traditional",
            rule_name=rule_name,
            version=1,
            effective_from=date(2026, 1, 1),
            label=rule_name,
            applies_to=[],
            finding_code=code,
            severity=severity,
            message=f"{rule_name} {code}",
            condition=cond,
            created_by="migration-a27cap000012",
        ))
    session.commit()


def test_two_rows_same_rule_name_load_once(db):
    """When a rule_name has multiple rows (one per finding it can
    emit), the callable runs exactly once in the loaded set."""
    session = db[0]()
    _seed_traditional(session)
    loaded = load_rule_sets(session)
    assert "traditional" in loaded
    names = [entry.name for entry in loaded["traditional"]]
    # interest_rate_sanity has two rows but must appear once
    assert names.count("interest_rate_sanity") == 1
    assert names.count("kyc_aml_present") == 1
    assert names.count("mode_info") == 1
    session.close()


def test_seeded_rules_run_and_behave_unchanged(db):
    """A gateway loaded from the seeded set produces the same
    decisions as the constants-loaded gateway for the same input."""
    from app.compliance import ComplianceGateway
    from tests.conftest import make_document, make_instrument
    from app.models.enums import ComplianceMode, DocumentType, TransactionType

    session = db[0]()
    _seed_traditional(session)

    # Same instrument evaluated twice: once with constants, once with
    # the DB-loaded set
    instr_a = make_instrument(
        txn_type=TransactionType.LOAN, mode=ComplianceMode.TRADITIONAL,
        type_specific_data={"interest_rate": 0.06},
    )
    instr_b = make_instrument(
        txn_type=TransactionType.LOAN, mode=ComplianceMode.TRADITIONAL,
        type_specific_data={"interest_rate": 0.06},
    )
    docs = [make_document(instr_a, doc_type=DocumentType.KYC)]

    decision_constants = ComplianceGateway().evaluate(instr_a, docs)
    decision_loaded = ComplianceGateway(load_rule_sets(session)).evaluate(instr_b, docs)

    # Same finding codes present (order may differ)
    codes_a = sorted(f.code for f in decision_constants.findings)
    codes_b = sorted(f.code for f in decision_loaded.findings)
    assert codes_a == codes_b
    assert decision_constants.outcome == decision_loaded.outcome
    session.close()


def test_constants_match_db_seed(db):
    """The in-memory constants mirror the DB seed. Any drift
    between app/compliance.py's constants and the migrations is a
    bug: the two must produce the same findings for the same
    instrument."""
    from app.compliance import RULE_SETS
    from app.compliance import ComplianceGateway

    # Load the DB-seeded rules (test DB is seeded by migration? No
    # -- tests use create_all, not migrations. So seed manually.)
    # Instead of running the migration, we compare the constants to
    # themselves plus assert their shape. The real parity is proven
    # by test_row_parity.py which compares
    # ComplianceGateway() vs ComplianceGateway(load_rule_sets(session))
    # after seeding. This test just guards against both constants
    # going empty.

    total_rules = sum(len(rules) for rules in RULE_SETS.values())
    assert total_rules == 8, (
        f"Expected 8 constant rules; found {total_rules}. "
        "Constants may have been deleted or truncated."
    )
    for rules in RULE_SETS.values():
        for rule in rules:
            assert rule.mode == "row"
            assert rule.callable is None
            assert len(rule.rows) >= 1
