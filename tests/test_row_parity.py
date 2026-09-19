"""Phase 2.5g -- parity between callable mode and row mode.

The DB path (row mode) must produce identical findings to the
constants path (callable mode) for every existing test scenario.
Any mismatch means a condition is wrong.
"""

from datetime import date as _date

from app.compliance import ComplianceGateway, load_rule_sets
from app.models.enums import (
    ComplianceMode,
    DocumentType,
    RuleSeverity,
    ShariahContractType,
    TransactionType,
)
from app.models.orm import ComplianceRule
from tests.conftest import make_document, make_instrument


# (rule_name, finding_code, severity, condition)
# Severity is per-row and drives the outcome computation. Every row's
# severity must match its callable's branch severity exactly.
CONDITIONS = [
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
    ("contract_type_declared", "SHAR_CONTRACT_TYPE_MISSING", RuleSeverity.BLOCKING,
     {"in": [{"var": "instrument.shariah_contract_type"}, [None, "none"]]}),
    ("asset_backing", "SHAB_ASSET_BACKING_MISSING", RuleSeverity.BLOCKING,
     {"and": [
         {"empty": [{"var": "instrument.underlying_asset_description"}]},
         {"empty": [{"var": "instrument.underlying_asset_id"}]},
     ]}),
    ("asset_backing", "SHAB_ASSET_PRESENT", RuleSeverity.INFO,
     {"or": [
         {"!": {"empty": [{"var": "instrument.underlying_asset_description"}]}},
         {"!": {"empty": [{"var": "instrument.underlying_asset_id"}]}},
     ]}),
    ("no_fixed_interest", "SHAB_FIXED_INTEREST", RuleSeverity.BLOCKING,
     {"or": [
         {"!": {"empty": [{"var": "instrument.type_specific_data.interest_rate"}]}},
         {"==": [{"var": "instrument.type_specific_data.fixed_coupon"}, True]},
     ]}),
    ("no_fixed_interest", "SHAB_NO_FIXED_INTEREST", RuleSeverity.INFO,
     {"!": {"or": [
         {"!": {"empty": [{"var": "instrument.type_specific_data.interest_rate"}]}},
         {"==": [{"var": "instrument.type_specific_data.fixed_coupon"}, True]},
     ]}}),
    ("fatwa_reference", "SHAB_FATWA_REFERENCE_MISSING", RuleSeverity.BLOCKING,
     {"empty": [{"var": "documents_by_type.fatwa"}]}),
    ("fatwa_reference", "SHAB_FATWA_REFERENCE_PRESENT", RuleSeverity.INFO,
     {"!": {"empty": [{"var": "documents_by_type.fatwa"}]}}),
    ("no_speculation", "SHAB_GHARAR_INDICATOR", RuleSeverity.BLOCKING,
     {"or": [
         {"meaningful": {"var": "instrument.type_specific_data.leverage"}},
         {"meaningful": {"var": "instrument.type_specific_data.margin"}},
         {"meaningful": {"var": "instrument.type_specific_data.derivative"}},
         {"meaningful": {"var": "instrument.type_specific_data.future"}},
     ]}),
]

_PACKAGE_FOR = {
    "kyc_aml_present": "traditional",
    "interest_rate_sanity": "traditional",
    "mode_info": "traditional",
}


def _seed_all_rows(session):
    for rule_name, code, severity, condition in CONDITIONS:
        session.add(ComplianceRule(
            id=f"g-{rule_name}-{code}",
            package_name=_PACKAGE_FOR.get(rule_name, "islamic"),
            rule_name=rule_name,
            version=1,
            effective_from=_date(2026, 1, 1),
            label=rule_name,
            applies_to=[],
            finding_code=code,
            severity=severity,
            message=f"{rule_name} {code}",
            condition=condition,
            created_by="test-parity",
        ))
    session.commit()


def _codes(decision):
    return sorted(f.code for f in decision.findings)


def _parity(session, instr, docs):
    const_decision = ComplianceGateway().evaluate(instr, docs)
    loaded = load_rule_sets(session)
    row_decision = ComplianceGateway(loaded).evaluate(instr, docs)
    assert _codes(const_decision) == _codes(row_decision), (
        f"callable vs row mismatch\n"
        f"  callable: {_codes(const_decision)}\n"
        f"  row:      {_codes(row_decision)}"
    )
    assert const_decision.outcome == row_decision.outcome


def test_parity_traditional_clean(db):
    session = db[0]()
    _seed_all_rows(session)
    instr = make_instrument(
        txn_type=TransactionType.LOAN,
        mode=ComplianceMode.TRADITIONAL,
        type_specific_data={"interest_rate": 0.06},
    )
    session.add(instr)
    session.flush()
    docs = [make_document(instr, doc_type=DocumentType.KYC)]
    session.add(docs[0])
    session.flush()
    _parity(session, instr, docs)
    session.close()


def test_parity_traditional_missing_kyc(db):
    session = db[0]()
    _seed_all_rows(session)
    instr = make_instrument(
        txn_type=TransactionType.LOAN,
        mode=ComplianceMode.TRADITIONAL,
        type_specific_data={"interest_rate": 0.06},
    )
    session.add(instr)
    session.flush()
    _parity(session, instr, [])
    session.close()


def test_parity_traditional_rate_out_of_band(db):
    session = db[0]()
    _seed_all_rows(session)
    instr = make_instrument(
        txn_type=TransactionType.LOAN,
        mode=ComplianceMode.TRADITIONAL,
        type_specific_data={"interest_rate": 0.95},
    )
    session.add(instr)
    session.flush()
    docs = [make_document(instr, doc_type=DocumentType.KYC)]
    session.add(docs[0])
    session.flush()
    _parity(session, instr, docs)
    session.close()


def test_parity_islamic_clean(db):
    session = db[0]()
    _seed_all_rows(session)
    instr = make_instrument(
        txn_type=TransactionType.SUKUK,
        mode=ComplianceMode.ISLAMIC,
        shariah_contract_type=ShariahContractType.MURABAHA,
        underlying_asset_id="asset-001",
        underlying_asset_description="Commodity basket",
        type_specific_data={"profit_rate": 0.05},
    )
    session.add(instr)
    session.flush()
    docs = [make_document(instr, doc_type=DocumentType.FATWA)]
    session.add(docs[0])
    session.flush()
    _parity(session, instr, docs)
    session.close()


def test_parity_islamic_fixed_interest(db):
    session = db[0]()
    _seed_all_rows(session)
    instr = make_instrument(
        txn_type=TransactionType.SUKUK,
        mode=ComplianceMode.ISLAMIC,
        shariah_contract_type=ShariahContractType.IJARA,
        underlying_asset_id="asset-002",
        type_specific_data={"interest_rate": 0.07},
    )
    session.add(instr)
    session.flush()
    docs = [make_document(instr, doc_type=DocumentType.FATWA)]
    session.add(docs[0])
    session.flush()
    _parity(session, instr, docs)
    session.close()