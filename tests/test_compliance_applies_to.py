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


# -----------------------------------------------------------------
# Loader round-trip: applies_to must flow from a DB row, through
# load_rule_sets, into the gateway. These tests go through the
# loader on purpose. The tests above exercise the filter in
# isolation; these prove the loader is the source of truth.
# -----------------------------------------------------------------

from app.compliance import load_rule_sets
from app.models.orm import ComplianceRule
from datetime import date


def _insert_scoped_rule(session, applies_to):
    """Insert one rule row with the given applies_to list. The
    row is keyed to 'mode_info' -- a callable that always emits an
    INFO finding, so its presence is easy to assert on."""
    session.add(ComplianceRule(
        id=f"loader-{'_'.join(applies_to) or 'all'}",
        package_name="traditional",
        rule_name="mode_info",
        version=1,
        effective_from=date(2026, 1, 1),
        label="mode_info",
        applies_to=applies_to,
        finding_code="TRAD_MODE_INFO",
        severity=RuleSeverity.INFO,
        message="mode info",
        condition={},
        created_by="test",
    ))
    # kyc_aml_present is not inserted, so the loaded set will only
    # contain mode_info for the traditional package. That's fine --
    # this test is about propagation, not about the complete set.
    session.commit()


def test_loader_propagates_applies_to_from_db_row(db):
    """A row inserted with applies_to=['loan'] must produce a loaded
    rule whose third tuple element is ['loan']."""
    session = db[0]()
    _insert_scoped_rule(session, ["loan"])

    loaded = load_rule_sets(session)
    assert "traditional" in loaded
    entry = next(
        (e for e in loaded["traditional"] if e[0] == "mode_info"),
        None,
    )
    assert entry is not None
    assert entry[2] == ["loan"], (
        f"loader dropped applies_to; got {entry[2]!r}"
    )
    session.close()


def test_loader_empty_applies_to_propagates_as_empty_list(db):
    """A row with applies_to=[] must produce a loaded rule with an
    empty list, meaning 'all types'."""
    session = db[0]()
    _insert_scoped_rule(session, [])

    loaded = load_rule_sets(session)
    entry = next(
        (e for e in loaded["traditional"] if e[0] == "mode_info"),
        None,
    )
    assert entry is not None
    assert entry[2] == []
    session.close()


def test_loader_scoped_rule_skipped_end_to_end(db):
    """A row scoped to 'loan' must not fire for an EQUITY instrument
    when the rules came from the loader -- the full pipeline from
    DB row to decision."""
    session = db[0]()
    _insert_scoped_rule(session, ["loan"])

    gateway = ComplianceGateway(load_rule_sets(session))
    instr = make_instrument(
        txn_type=TransactionType.EQUITY,
        mode=ComplianceMode.TRADITIONAL,
        type_specific_data={"interest_rate": 0.06},
    )
    decision = gateway.evaluate(instr, [])
    assert not any(
        f.code == "TRAD_MODE_INFO" for f in decision.findings
    ), "scoped rule ran for a non-matching transaction_type"
    session.close()
