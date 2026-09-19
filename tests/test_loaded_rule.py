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

# -----------------------------------------------------------------
# Phase 2.5e -- LoadedRule carries row metadata for later
# row-driven emission. The engine is unchanged; the list is
# populated and tested but not yet read.
# -----------------------------------------------------------------


def test_constant_rules_have_empty_rows():
    """Constants carry a callable but no DB row metadata."""
    for rules in RULE_SETS.values():
        for rule in rules:
            assert rule.callable is not None
            assert rule.rows == []


def test_loader_preserves_all_rows_for_shared_rule_name(db):
    """A rule_name with two DB rows must produce a LoadedRule whose
    rows list has both entries. This is the shape 2.5f needs."""
    from datetime import date as _date

    session = db[0]()
    session.add(ComplianceRule(
        id="rate-missing",
        package_name="traditional",
        rule_name="interest_rate_sanity",
        version=1,
        effective_from=_date(2026, 1, 1),
        label="rate presence",
        applies_to=[],
        finding_code="TRAD_RATE_MISSING",
        severity=RuleSeverity.REVIEW,
        message="No interest_rate on record.",
        condition={},
        created_by="test",
    ))
    session.add(ComplianceRule(
        id="rate-oob",
        package_name="traditional",
        rule_name="interest_rate_sanity",
        version=1,
        effective_from=_date(2026, 1, 1),
        label="rate bounds",
        applies_to=[],
        finding_code="TRAD_RATE_OUT_OF_BAND",
        severity=RuleSeverity.BLOCKING,
        message="Interest rate outside acceptable band.",
        condition={},
        created_by="test",
    ))
    session.commit()

    loaded = load_rule_sets(session)
    entry = next(
        (r for r in loaded["traditional"] if r.name == "interest_rate_sanity"),
        None,
    )
    assert entry is not None
    assert len(entry.rows) == 2
    codes = sorted(r["finding_code"] for r in entry.rows)
    assert codes == ["TRAD_RATE_MISSING", "TRAD_RATE_OUT_OF_BAND"]
    # Severity is preserved per row
    by_code = {r["finding_code"]: r["severity"] for r in entry.rows}
    assert by_code["TRAD_RATE_MISSING"] == RuleSeverity.REVIEW
    assert by_code["TRAD_RATE_OUT_OF_BAND"] == RuleSeverity.BLOCKING
    session.close()


def test_loader_row_metadata_has_all_five_keys(db):
    """Each row dict has exactly: applies_to, condition,
    finding_code, severity, message_template."""
    from datetime import date as _date

    session = db[0]()
    session.add(ComplianceRule(
        id="shape-test",
        package_name="traditional",
        rule_name="mode_info",
        version=1,
        effective_from=_date(2026, 1, 1),
        label="mode",
        applies_to=["loan"],
        finding_code="TRAD_MODE_INFO",
        severity=RuleSeverity.INFO,
        message="Mode message.",
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
    assert len(entry.rows) == 1
    row = entry.rows[0]
    assert set(row.keys()) == {
        "applies_to", "condition", "finding_code",
        "severity", "message_template",
    }
    assert row["applies_to"] == ["loan"]
    assert row["condition"] == {"==": [1, 1]}
    assert row["finding_code"] == "TRAD_MODE_INFO"
    assert row["severity"] == RuleSeverity.INFO
    assert row["message_template"] == "Mode message."
    session.close()


def test_loader_row_without_callable_loads_with_none(db):
    """A row whose rule_name has no matching Python callable loads
    with callable=None and rows populated. It is inert in 2.5e."""
    from datetime import date as _date

    session = db[0]()
    session.add(ComplianceRule(
        id="orphan",
        package_name="traditional",
        rule_name="no_such_python_rule",
        version=1,
        effective_from=_date(2026, 1, 1),
        label="orphan",
        applies_to=[],
        finding_code="ORPHAN_CODE",
        severity=RuleSeverity.INFO,
        message="Orphan message.",
        condition={"==": [1, 1]},
        created_by="test",
    ))
    session.commit()

    loaded = load_rule_sets(session)
    entry = next(
        (r for r in loaded["traditional"] if r.name == "no_such_python_rule"),
        None,
    )
    assert entry is not None
    assert entry.callable is None
    assert len(entry.rows) == 1
    assert entry.rows[0]["finding_code"] == "ORPHAN_CODE"
    session.close()


def test_engine_behavior_unchanged_for_constants():
    """Running the gateway on a clean instrument still produces the
    same findings as before 2.5e. The rows list is not read."""
    from app.models.enums import TransactionType

    instr = make_instrument(
        txn_type=TransactionType.LOAN,
        mode=ComplianceMode.TRADITIONAL,
        type_specific_data={"interest_rate": 0.06},
    )
    # No KYC -> the KYC rule fires
    decision = ComplianceGateway().evaluate(instr, [])
    assert any(f.code == "TRAD_KYC_MISSING" for f in decision.findings)

