"""Phase 2 — compliance-as-configuration: one gateway, two rule sets."""

import pytest
from datetime import date

from app.compliance import (
    ComplianceGateway,
    RULE_SETS,
    run_gateway_with_ledger,
)
from app.models.enums import (
    ComplianceMode,
    DocumentType,
    RuleSeverity,
    ShariahContractType,
    ShariahReviewStatus,
    TransactionType,
)
from app.models.orm import ComplianceRule
from app.telemetry import clear_traces, find_trace
from tests.conftest import make_document, make_instrument


@pytest.fixture(autouse=True)
def _clean_traces():
    clear_traces()
    yield


def test_traditional_clean_passes_not_applicable(db):
    session = db[0]()
    instr = make_instrument(
        txn_type=TransactionType.LOAN,
        mode=ComplianceMode.TRADITIONAL,
        type_specific_data={"interest_rate": 0.06},
    )
    session.add(instr)
    session.flush()
    docs = [make_document(instr, doc_type=DocumentType.KYC)]

    decision = ComplianceGateway().evaluate(instr, docs)
    assert decision.outcome == ShariahReviewStatus.NOT_APPLICABLE
    assert not decision.blocking
    session.close()


def test_traditional_flagged_for_missing_kyc(db):
    session = db[0]()
    instr = make_instrument(
        txn_type=TransactionType.LOAN,
        mode=ComplianceMode.TRADITIONAL,
        type_specific_data={"interest_rate": 0.06},
    )
    session.add(instr)
    session.flush()
    # No KYC document attached -> blocking
    decision = ComplianceGateway().evaluate(instr, [])
    assert decision.outcome == ShariahReviewStatus.SYSTEM_FLAGGED_NONCOMPLIANT
    assert any(f.code == "TRAD_KYC_MISSING" for f in decision.findings)
    session.close()


def test_traditional_flagged_for_out_of_band_rate(db):
    session = db[0]()
    instr = make_instrument(
        txn_type=TransactionType.LOAN,
        mode=ComplianceMode.TRADITIONAL,
        type_specific_data={"interest_rate": 0.95},
    )
    session.add(instr)
    session.flush()
    docs = [make_document(instr, doc_type=DocumentType.KYC)]
    decision = ComplianceGateway().evaluate(instr, docs)
    assert decision.outcome == ShariahReviewStatus.SYSTEM_FLAGGED_NONCOMPLIANT
    assert any(f.code == "TRAD_RATE_OUT_OF_BAND" for f in decision.findings)
    session.close()


def test_islamic_clean_lands_pending_not_approved(db):
    session = db[0]()
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

    decision = ComplianceGateway().evaluate(instr, docs)
    assert decision.outcome == ShariahReviewStatus.PENDING_SCHOLAR_REVIEW
    assert not decision.blocking
    session.close()


def test_islamic_fixed_interest_flagged_automatically(db):
    session = db[0]()
    instr = make_instrument(
        txn_type=TransactionType.SUKUK,
        mode=ComplianceMode.ISLAMIC,
        shariah_contract_type=ShariahContractType.IJARA,
        underlying_asset_id="asset-002",
        type_specific_data={"interest_rate": 0.07},  # forbidden on Islamic track
    )
    session.add(instr)
    session.flush()
    docs = [make_document(instr, doc_type=DocumentType.FATWA)]

    decision = ComplianceGateway().evaluate(instr, docs)
    assert decision.outcome == ShariahReviewStatus.SYSTEM_FLAGGED_NONCOMPLIANT
    assert any(f.code == "SHAB_FIXED_INTEREST" for f in decision.findings)
    session.close()


def test_gateway_emits_trace(db):
    session = db[0]()
    instr = make_instrument(
        txn_type=TransactionType.SUKUK,
        mode=ComplianceMode.ISLAMIC,
        shariah_contract_type=ShariahContractType.MURABAHA,
        underlying_asset_id="a",
        type_specific_data={"profit_rate": 0.05})
    session.add(instr)
    session.flush()
    docs = [make_document(instr, doc_type=DocumentType.FATWA)]
    session.add(docs[0])
    session.flush()  # FK-order: ledger rows may only reference persisted documents
    run_gateway_with_ledger(session, instr, docs)
    trace = find_trace("compliance.gateway")
    assert trace is not None, "gateway decision must emit a telemetry trace"
    assert trace.metadata["rule_set"] == "islamic"
    session.close()


def test_compliance_rule_severity_values(db):
    """RuleSeverity must carry exactly the three documented values."""
    session = db[0]()
    assert RuleSeverity.BLOCKING.value == "blocking"
    assert RuleSeverity.REVIEW.value == "review"
    assert RuleSeverity.INFO.value == "info"
    assert len(list(RuleSeverity)) == 3
    session.close()


def test_compliance_rule_can_be_persisted(db):
    """A ComplianceRule can be constructed, persisted and read back."""
    session = db[0]()
    rule = ComplianceRule(
        id="rule-001",
        package_name="flowgate.core",
        rule_name="max-investment",
        version=1,
        effective_from=date(2026, 1, 1),
        label="Maximum investment per deal",
        description="No single deal may exceed the configured cap.",
        finding_code="CFG_MAX_INVESTMENT",
        severity=RuleSeverity.BLOCKING,
        message="Investment exceeds maximum allowed.",
        condition={},
        created_by="system",
    )
    session.add(rule)
    session.flush()
    session.expunge(rule)
    fetched = session.get(ComplianceRule, "rule-001")
    assert fetched is not None
    assert fetched.package_name == "flowgate.core"
    assert fetched.rule_name == "max-investment"
    assert fetched.severity == RuleSeverity.BLOCKING
    assert fetched.active is True
    assert fetched.version == 1
    assert fetched.created_by == "system"
    session.close()


def test_compliance_rule_json_fields(db):
    """applies_to and condition are JSON columns with the expected defaults."""
    session = db[0]()
    rule = ComplianceRule(
        id="rule-002",
        package_name="flowgate.core",
        rule_name="type-restricted",
        version=1,
        effective_from=date(2026, 1, 1),
        label="Type restricted rule",
        finding_code="CFG_TYPE_OK",
        severity=RuleSeverity.INFO,
        message="Type check passed.",
        applies_to=["equity", "sukuk"],
        condition={"and": [{"==": ["$var", "allowed"]}]},
        created_by="system",
    )
    session.add(rule)
    session.flush()
    fetched = session.get(ComplianceRule, "rule-002")
    assert fetched.applies_to == ["equity", "sukuk"]
    assert fetched.condition == {"and": [{"==": ["$var", "allowed"]}]}
    # Default values when not supplied.
    default_rule = ComplianceRule(
        id="rule-003",
        package_name="flowgate.core",
        rule_name="default-rule",
        version=1,
        effective_from=date(2026, 1, 1),
        label="Default rule",
        finding_code="CFG_DEFAULT",
        severity=RuleSeverity.INFO,
        message="Default rule.",
        created_by="system",
    )
    session.add(default_rule)
    session.flush()
    fetched_default = session.get(ComplianceRule, "rule-003")
    assert fetched_default.applies_to == []
    assert fetched_default.condition == {}
    session.close()


def test_compliance_rule_version_and_effective_dates(db):
    """Version and effective-date fields persist without truncating history."""
    session = db[0]()
    original = ComplianceRule(
        id="rule-v1",
        package_name="flowgate.core",
        rule_name="threshold",
        version=1,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 5, 31),
        label="Threshold v1",
        finding_code="CFG_THRESHOLD",
        severity=RuleSeverity.REVIEW,
        message="Original threshold.",
        active=True,
        created_by="system",
    )
    session.add(original)
    session.flush()

    # A later version gets its own effective_from; the previous row keeps
    # its effective_to so history is not truncated.
    replacement = ComplianceRule(
        id="rule-v2",
        package_name="flowgate.core",
        rule_name="threshold",
        version=2,
        effective_from=date(2026, 6, 1),
        effective_to=None,
        label="Threshold v2",
        finding_code="CFG_THRESHOLD",
        severity=RuleSeverity.BLOCKING,
        message="Updated threshold.",
        active=True,
        created_by="system",
    )
    session.add(replacement)
    session.flush()
    session.expunge(original)
    fetched = session.get(ComplianceRule, "rule-v1")
    assert fetched.version == 1
    assert fetched.effective_from == date(2026, 1, 1)
    assert fetched.effective_to == date(2026, 5, 31)
    assert fetched.active is True
    session.close()


def test_never_approves():
    instr = make_instrument(txn_type=TransactionType.SUKUK, mode=ComplianceMode.ISLAMIC,
                            shariah_contract_type=ShariahContractType.IJARA,
                            underlying_asset_description="x")
    docs = []
    decision = ComplianceGateway().evaluate(instr, docs)
    assert decision.outcome not in {
        ShariahReviewStatus.SCHOLAR_APPROVED,
        ShariahReviewStatus.SCHOLAR_REJECTED,
    }