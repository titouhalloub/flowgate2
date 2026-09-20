"""Phase 2.9 -- multi-jurisdiction composition.

evaluate() accepts extra_jurisdictions; findings merge across
every loaded package; BLOCKING from any package wins.
"""

from app.compliance import (
    ComplianceGateway,
    LoadedRule,
    RuleFinding,
)
from app.models.enums import (
    ComplianceMode,
    RuleSeverity,
    ShariahReviewStatus,
    TransactionType,
)
from tests.conftest import make_instrument


def _info_rule(name):
    def fn(ctx):
        return [RuleFinding(
            code=f"{name}_FIRED",
            severity=RuleSeverity.INFO,
            message=f"{name} fired",
        )]
    return LoadedRule(
        name=name, callable=fn, applies_to=[],
    )


def _blocking_rule(name):
    def fn(ctx):
        return [RuleFinding(
            code=f"{name}_BLOCKED",
            severity=RuleSeverity.BLOCKING,
            message=f"{name} blocked",
        )]
    return LoadedRule(
        name=name, callable=fn, applies_to=[],
    )


def test_extra_jurisdiction_findings_merge():
    gateway = ComplianceGateway({
        "traditional": [_info_rule("trad")],
        "difc": [_info_rule("difc")],
    })
    instr = make_instrument(
        txn_type=TransactionType.LOAN,
        mode=ComplianceMode.TRADITIONAL,
    )
    decision = gateway.evaluate(
        instr, [],
        extra_jurisdictions=["difc"],
    )
    codes = sorted(f.code for f in decision.findings)
    assert codes == ["difc_FIRED", "trad_FIRED"]


def test_blocking_from_extra_jurisdiction_wins():
    gateway = ComplianceGateway({
        "traditional": [_info_rule("trad")],
        "difc": [_blocking_rule("difc")],
    })
    instr = make_instrument(
        txn_type=TransactionType.LOAN,
        mode=ComplianceMode.TRADITIONAL,
    )
    decision = gateway.evaluate(
        instr, [],
        extra_jurisdictions=["difc"],
    )
    assert decision.outcome == ShariahReviewStatus.SYSTEM_FLAGGED_NONCOMPLIANT


def test_unknown_jurisdiction_reports_info_not_error():
    gateway = ComplianceGateway({
        "traditional": [_info_rule("trad")],
    })
    instr = make_instrument(
        txn_type=TransactionType.LOAN,
        mode=ComplianceMode.TRADITIONAL,
    )
    decision = gateway.evaluate(
        instr, [],
        extra_jurisdictions=["adgm", "sama"],
    )
    codes = sorted(f.code for f in decision.findings)
    assert codes.count("JURISDICTION_NOT_LOADED") == 2
    # INFO findings do not flip the outcome
    assert decision.outcome == ShariahReviewStatus.NOT_APPLICABLE


def test_no_extra_jurisdictions_preserves_behavior():
    gateway = ComplianceGateway({
        "traditional": [_info_rule("trad")],
    })
    instr = make_instrument(
        txn_type=TransactionType.LOAN,
        mode=ComplianceMode.TRADITIONAL,
    )
    a = gateway.evaluate(instr, [])
    b = gateway.evaluate(instr, [], extra_jurisdictions=[])
    assert sorted(f.code for f in a.findings) == sorted(
        f.code for f in b.findings
    )


def test_duplicate_of_primary_is_not_run_twice():
    gateway = ComplianceGateway({
        "traditional": [_info_rule("trad")],
    })
    instr = make_instrument(
        txn_type=TransactionType.LOAN,
        mode=ComplianceMode.TRADITIONAL,
    )
    decision = gateway.evaluate(
        instr, [],
        extra_jurisdictions=["traditional"],
    )
    codes = [f.code for f in decision.findings]
    assert codes.count("trad_FIRED") == 1
