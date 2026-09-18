"""Phase 2.4 -- applies_to filtering.

A rule with a non-empty applies_to list runs only for instruments
whose transaction_type is in the list. Rules with an empty applies_to
run for all instrument types (current behavior).
"""

from app.compliance import ComplianceGateway, RULE_SETS
from app.models.enums import (
    ComplianceMode,
    DocumentType,
    RuleSeverity,
    TransactionType,
)
from tests.conftest import make_document, make_instrument


def _gateway_with_scoped_rule():
    """A gateway whose traditional set carries one loan-scoped rule."""
    loan_scoped = []
    for name, fn, applies in RULE_SETS["traditional"]:
        if name == "kyc_aml_present":
            loan_scoped.append((name, fn, ["loan"]))
        else:
            loan_scoped.append((name, fn, applies))
    return ComplianceGateway({
        "traditional": loan_scoped,
        "islamic": list(RULE_SETS["islamic"]),
    })


def test_empty_applies_to_runs_for_all_types():
    gateway = ComplianceGateway()
    for txn_type in (
        TransactionType.LOAN,
        TransactionType.EQUITY,
        TransactionType.SUKUK,
    ):
        instr = make_instrument(
            txn_type=txn_type, mode=ComplianceMode.TRADITIONAL,
            type_specific_data={"interest_rate": 0.06},
        )
        docs = [make_document(instr, doc_type=DocumentType.KYC)]
        decision = gateway.evaluate(instr, docs)
        # The KYC rule ran (present doc -> no missing finding, and no
        # blocking finding from the empty-applies_to rule set)
        assert not any(
            f.code == "TRAD_KYC_MISSING" for f in decision.findings
        )
        assert not any(
            f.severity == RuleSeverity.BLOCKING for f in decision.findings
        )


def test_scoped_rule_skipped_for_other_types():
    gateway = _gateway_with_scoped_rule()
    instr = make_instrument(
        txn_type=TransactionType.EQUITY, mode=ComplianceMode.TRADITIONAL,
        type_specific_data={"interest_rate": 0.06},
    )
    # No KYC doc: the scoped kyc rule would flag if it ran -- it must not
    decision = gateway.evaluate(instr, [])
    assert not any(
        f.code == "TRAD_KYC_MISSING" for f in decision.findings
    )


def test_scoped_rule_runs_for_matching_type():
    gateway = _gateway_with_scoped_rule()
    instr = make_instrument(
        txn_type=TransactionType.LOAN, mode=ComplianceMode.TRADITIONAL,
        type_specific_data={"interest_rate": 0.06},
    )
    # No KYC doc: the scoped rule applies to loans and must flag
    decision = gateway.evaluate(instr, [])
    assert any(
        f.code == "TRAD_KYC_MISSING" for f in decision.findings
    )
