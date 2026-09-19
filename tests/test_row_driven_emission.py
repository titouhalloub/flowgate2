"""Phase 2.5f -- row-driven emission.

A LoadedRule in mode="row" emits one RuleFinding per row whose
condition evaluates true. Callable mode is unchanged.
"""

import pytest

from app.compliance import ComplianceGateway, LoadedRule
from app.models.enums import (
    ComplianceMode,
    RuleSeverity,
    ShariahReviewStatus,
    TransactionType,
)
from tests.conftest import make_instrument


def _row_rule(condition, code, severity, message="msg"):
    return LoadedRule(
        name="row-rule",
        callable=None,
        applies_to=[],
        condition=condition,
        rows=[{
            "applies_to": [],
            "condition": condition,
            "finding_code": code,
            "severity": severity,
            "message_template": message,
        }],
        mode="row",
    )


def test_row_mode_emits_when_condition_true():
    rule = _row_rule(
        {"==": [1, 1]},
        "TRAD_MODE_INFO",
        RuleSeverity.INFO,
        "row emitted",
    )
    gateway = ComplianceGateway({"traditional": [rule]})
    instr = make_instrument(
        txn_type=TransactionType.LOAN,
        mode=ComplianceMode.TRADITIONAL,
    )
    decision = gateway.evaluate(instr, [])
    assert any(f.code == "TRAD_MODE_INFO" for f in decision.findings)
    assert any(
        f.message == "row emitted" for f in decision.findings
    )


def test_row_mode_skips_when_condition_false():
    rule = _row_rule(
        {"==": [1, 0]},
        "TRAD_MODE_INFO",
        RuleSeverity.INFO,
    )
    gateway = ComplianceGateway({"traditional": [rule]})
    instr = make_instrument(
        txn_type=TransactionType.LOAN,
        mode=ComplianceMode.TRADITIONAL,
    )
    decision = gateway.evaluate(instr, [])
    assert not any(
        f.code == "TRAD_MODE_INFO" for f in decision.findings
    )


def test_row_mode_emits_one_finding_per_matching_row():
    rule = LoadedRule(
        name="multi",
        callable=None,
        applies_to=[],
        condition={},
        rows=[
            {
                "applies_to": [],
                "condition": {"==": [1, 1]},
                "finding_code": "ROW_A",
                "severity": RuleSeverity.INFO,
                "message_template": "a",
            },
            {
                "applies_to": [],
                "condition": {"==": [1, 0]},
                "finding_code": "ROW_B",
                "severity": RuleSeverity.INFO,
                "message_template": "b",
            },
            {
                "applies_to": [],
                "condition": {"==": [1, 1]},
                "finding_code": "ROW_C",
                "severity": RuleSeverity.INFO,
                "message_template": "c",
            },
        ],
        mode="row",
    )
    gateway = ComplianceGateway({"traditional": [rule]})
    instr = make_instrument(
        txn_type=TransactionType.LOAN,
        mode=ComplianceMode.TRADITIONAL,
    )
    decision = gateway.evaluate(instr, [])
    codes = sorted(f.code for f in decision.findings)
    assert codes == ["ROW_A", "ROW_C"]


def test_row_mode_empty_condition_row_is_skipped():
    """A row with condition={} is never emitted in row mode."""
    rule = LoadedRule(
        name="mixed",
        callable=None,
        applies_to=[],
        condition={},
        rows=[{
            "applies_to": [],
            "condition": {},
            "finding_code": "NEVER",
            "severity": RuleSeverity.INFO,
            "message_template": "never",
        }],
        mode="row",
    )
    gateway = ComplianceGateway({"traditional": [rule]})
    instr = make_instrument(
        txn_type=TransactionType.LOAN,
        mode=ComplianceMode.TRADITIONAL,
    )
    decision = gateway.evaluate(instr, [])
    assert not any(f.code == "NEVER" for f in decision.findings)


def test_row_mode_blocking_finding_flags_noncompliant():
    rule = _row_rule(
        {"==": [1, 1]},
        "ROW_BLOCK",
        RuleSeverity.BLOCKING,
    )
    gateway = ComplianceGateway({"traditional": [rule]})
    instr = make_instrument(
        txn_type=TransactionType.LOAN,
        mode=ComplianceMode.TRADITIONAL,
    )
    decision = gateway.evaluate(instr, [])
    assert decision.outcome == ShariahReviewStatus.SYSTEM_FLAGGED_NONCOMPLIANT


def test_callable_mode_still_wins_by_default():
    """A LoadedRule without an explicit mode defaults to callable
    and behaves exactly as pre-2.5f."""
    rule = LoadedRule(
        name="legacy",
        callable=lambda ctx: [],
        applies_to=[],
        condition={},
        rows=[],
    )
    assert rule.mode == "callable"
