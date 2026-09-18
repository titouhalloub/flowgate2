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
