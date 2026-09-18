"""Phase 2.2 -- load_rule_sets. Behavior is unchanged when the table
is empty; the DB becomes the source of truth only once rows exist."""

from datetime import date

from app.compliance import load_rule_sets, RULE_SETS
from app.models.enums import RuleSeverity
from app.models.orm import ComplianceRule


def test_empty_table_falls_back_to_constants(db):
    """No rows -> the module constants are returned unchanged."""
    session = db[0]()
    loaded = load_rule_sets(session)
    assert loaded is RULE_SETS
    session.close()


def test_none_session_falls_back_to_constants():
    """No session -> the module constants are returned unchanged."""
    loaded = load_rule_sets(None)
    assert loaded is RULE_SETS


def test_rule_missing_from_db_does_not_run(db):
    """When rows exist for a package, only rows present in the DB run.
    A rule present in the constants but missing from the DB is
    excluded."""
    session = db[0]()

    # Insert all traditional rules except kyc_aml_present
    rows = [
        ("interest_rate_sanity", "TRAD_RATE_MISSING", RuleSeverity.REVIEW),
        ("mode_info", "TRAD_MODE_INFO", RuleSeverity.INFO),
    ]
    for rule_name, code, severity in rows:
        session.add(ComplianceRule(
            id=f"test-{rule_name}",
            package_name="traditional",
            rule_name=rule_name,
            version=1,
            effective_from=date(2026, 1, 1),
            label=rule_name,
            applies_to=[],
            finding_code=code,
            severity=severity,
            message=f"{rule_name} message",
            condition={},
            created_by="test",
        ))
    session.commit()

    loaded = load_rule_sets(session)
    assert "traditional" in loaded
    names = [entry.name for entry in loaded["traditional"]]  
    assert "interest_rate_sanity" in names
    assert "mode_info" in names
    assert "kyc_aml_present" not in names
    session.close()