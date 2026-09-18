"""Phase 2.5c -- LoadedRule dataclass and loader propagation.

Structural refactor only. Behavior is unchanged: every row's
condition is {} and the engine still runs every callable. These
tests pin the new shape.
"""

from datetime import date

from app.compliance import (
    ComplianceGateway,
    LoadedRule,
    RULE_SETS,
    load_rule_sets,
)
from app.models.enums import RuleSeverity
from app.models.orm import ComplianceRule


def test_loaded_rule_is_frozen():
    """LoadedRule instances are immutable after construction."""
    rule = LoadedRule(
        name="test",
        callable=lambda ctx: [],
        applies_to=[],
    )
    import pytest
    with pytest.raises(Exception):
        rule.name = "changed"


def test_loaded_rule_default_condition_is_empty_dict():
    rule = LoadedRule(
        name="test",
        callable=lambda ctx: [],
        applies_to=[],
    )
    assert rule.condition == {}


def test_constants_are_loaded_rule_instances():
    for rules in RULE_SETS.values():
        for rule in rules:
            assert isinstance(rule, LoadedRule)
            assert callable(rule.callable)
            assert isinstance(rule.applies_to, list)


def test_loader_propagates_condition_from_db_row(db):
    """A row with a non-empty condition must produce a LoadedRule
    whose condition matches it. The engine does not use this yet,
    but the loader must carry it."""
    session = db[0]()
    session.add(ComplianceRule(
        id="cond-test",
        package_name="traditional",
        rule_name="mode_info",
        version=1,
        effective_from=date(2026, 1, 1),
        label="mode_info",
        applies_to=[],
        finding_code="TRAD_MODE_INFO",
        severity=RuleSeverity.INFO,
        message="mode info",
        condition={"==": [1, 1]},
        created_by="test",
    ))
    session.commit()

    loaded = load_rule_sets(session)
    entry = next(
        (r for r in loaded["traditional"] if r.name == "mode_info"),
        None,
    )
    assert entry is not None
    assert entry.condition == {"==": [1, 1]}
    session.close()


def test_loader_defaults_missing_condition_to_empty_dict(db):
    """A row with condition=None produces condition={} on the
    LoadedRule."""
    session = db[0]()
    session.add(ComplianceRule(
        id="no-cond-test",
        package_name="traditional",
        rule_name="mode_info",
        version=1,
        effective_from=date(2026, 1, 1),
        label="mode_info",
        applies_to=[],
        finding_code="TRAD_MODE_INFO",
        severity=RuleSeverity.INFO,
        message="mode info",
        condition=None,
        created_by="test",
    ))
    session.commit()

    loaded = load_rule_sets(session)
    entry = next(
        (r for r in loaded["traditional"] if r.name == "mode_info"),
        None,
    )
    assert entry is not None
    assert entry.condition == {}
    session.close()


# -----------------------------------------------------------------
# Phase 2.5d -- condition gate in evaluate(). A LoadedRule with a
# non-empty condition runs its callable only when the condition is
# true. A LoadedRule with an empty condition runs unconditionally
# (pre-2.5d behavior preserved).
# -----------------------------------------------------------------

from dataclasses import replace as _replace

from app.compliance import build_context  # noqa: F401 -- smoke import
from app.models.enums import (
    ComplianceMode,
    DocumentType,
    TransactionType,
)
from tests.conftest import make_document, make_instrument


def test_gate_skips_rule_when_condition_false():
    """A rule with a condition that always evaluates false must not
    produce findings, even though its callable would."""
    instr = make_instrument(
        txn_type=TransactionType.LOAN,
        mode=ComplianceMode.TRADITIONAL,
        type_specific_data={"interest_rate": 0.06},
    )
    # No KYC doc attached -> the callable WOULD emit TRAD_KYC_MISSING.
    # But the condition forbids running.
    docs = []

    # Start from the constants, then override kyc_aml_present's
    # condition to always false.
    scoped = []
    for rule in RULE_SETS["traditional"]:
        if rule.name == "kyc_aml_present":
            scoped.append(_replace(
                rule, condition={"==": [1, 0]},
            ))
        else:
            scoped.append(rule)
    gateway = ComplianceGateway({
        "traditional": scoped,
        "islamic": list(RULE_SETS["islamic"]),
    })

    decision = gateway.evaluate(instr, docs)
    assert not any(
        f.code == "TRAD_KYC_MISSING" for f in decision.findings
    ), "gate failed: rule ran despite false condition"


def test_gate_runs_rule_when_condition_true():
    """A rule with a condition that always evaluates true produces
    its normal findings."""
    instr = make_instrument(
        txn_type=TransactionType.LOAN,
        mode=ComplianceMode.TRADITIONAL,
        type_specific_data={"interest_rate": 0.06},
    )
    docs = []

    scoped = []
    for rule in RULE_SETS["traditional"]:
        if rule.name == "kyc_aml_present":
            scoped.append(_replace(
                rule, condition={"==": [1, 1]},
            ))
        else:
            scoped.append(rule)
    gateway = ComplianceGateway({
        "traditional": scoped,
        "islamic": list(RULE_SETS["islamic"]),
    })

    decision = gateway.evaluate(instr, docs)
    assert any(
        f.code == "TRAD_KYC_MISSING" for f in decision.findings
    ), "gate failed: rule did not run despite true condition"


def test_gate_is_no_op_for_empty_condition():
    """A rule with condition={} runs unconditionally, identical to
    pre-2.5d behavior."""
    instr = make_instrument(
        txn_type=TransactionType.LOAN,
        mode=ComplianceMode.TRADITIONAL,
        type_specific_data={"interest_rate": 0.06},
    )
    docs = []

    # Default gateway: all conditions are {}
    decision = ComplianceGateway().evaluate(instr, docs)
    assert any(
        f.code == "TRAD_KYC_MISSING" for f in decision.findings
    )


def test_gate_uses_instrument_context():
    """The condition receives the serialized context, so it can read
    the instrument's transaction_type and type_specific_data."""
    instr = make_instrument(
        txn_type=TransactionType.LOAN,
        mode=ComplianceMode.TRADITIONAL,
        type_specific_data={"interest_rate": 0.06},
    )
    docs = []

    # Condition: only run when transaction_type == "loan". This is
    # true for the fixture, so the rule runs.
    scoped = []
    for rule in RULE_SETS["traditional"]:
        if rule.name == "kyc_aml_present":
            scoped.append(_replace(
                rule,
                condition={
                    "==": [
                        {"var": "instrument.transaction_type"},
                        "loan",
                    ],
                },
            ))
        else:
            scoped.append(rule)
    gateway = ComplianceGateway({
        "traditional": scoped,
        "islamic": list(RULE_SETS["islamic"]),
    })

    decision = gateway.evaluate(instr, docs)
    assert any(
        f.code == "TRAD_KYC_MISSING" for f in decision.findings
    )


def test_gate_context_false_for_non_matching_type():
    """Same condition, different transaction_type: the rule is
    skipped."""
    instr = make_instrument(
        txn_type=TransactionType.EQUITY,
        mode=ComplianceMode.TRADITIONAL,
        type_specific_data={"interest_rate": 0.06},
    )
    docs = []

    scoped = []
    for rule in RULE_SETS["traditional"]:
        if rule.name == "kyc_aml_present":
            scoped.append(_replace(
                rule,
                condition={
                    "==": [
                        {"var": "instrument.transaction_type"},
                        "loan",
                    ],
                },
            ))
        else:
            scoped.append(rule)
    gateway = ComplianceGateway({
        "traditional": scoped,
        "islamic": list(RULE_SETS["islamic"]),
    })

    decision = gateway.evaluate(instr, docs)
    assert not any(
        f.code == "TRAD_KYC_MISSING" for f in decision.findings
    )

