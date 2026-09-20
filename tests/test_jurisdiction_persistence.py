"""Phase 2.10 -- jurisdictions persisted on Instrument.

After this sub-phase, submitting a document without an explicit
jurisdictions override uses the instrument's stored jurisdictions.
"""

from datetime import date

from app.models.enums import (
    ComplianceMode,
    RuleSeverity,
    TransactionType,
)
from app.models.orm import ComplianceRule

HEADERS = {"X-API-Key": "test-key-123"}

LOAN_TEXT = (
    "LOAN AGREEMENT\n"
    "Borrower: Test Co\n"
    "Lender: Meridian Bank\n"
    "Principal: USD 2,500,000\n"
    "Interest Rate: 6.5%\n"
    "Repayment: quarterly amortization over 5 years\n"
    "Maturity Date: 2029-12-31\n"
    "Governing Law: English Law\n"
    "All KYC and AML certifications have been validated and archived.\n"
)


def _seed_difc_rule(session):
    """Seed a DIFC package row so composition has a real target."""
    session.add(ComplianceRule(
        id="difc-test-rule",
        package_name="difc",
        rule_name="difc_test_blocker",
        version=1,
        effective_from=date(2026, 1, 1),
        label="DIFC test blocker",
        applies_to=[],
        finding_code="DIFC_TEST_BLOCK",
        severity=RuleSeverity.BLOCKING,
        message="DIFC test rule fired.",
        condition={"empty": [{"var": "documents_by_type.kyc"}]},
        created_by="test",
    ))
    session.commit()


def test_instrument_stores_jurisdictions(client):
    r = client.post("/instruments", headers=HEADERS, json={
        "transaction_type": "loan",
        "compliance_mode": "traditional",
        "issuer_name": "Jurisdiction Test Co",
        "issuer_type": "Corporate",
        "amount": 1000000,
        "currency": "USD",
        "jurisdictions": ["difc", "cayman"],
    })
    assert r.status_code == 201, r.text
    # Confirm the round-trip via a GET
    inst_id = r.json()["id"]
    r2 = client.get(f"/instruments/{inst_id}", headers=HEADERS)
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body.get("jurisdictions") == ["difc", "cayman"]


def test_submission_uses_instrument_jurisdictions(client, db):
    _seed_difc_rule(db[0]())

    # Instrument has DIFC, so a clean submission should compose.
    r = client.post("/instruments", headers=HEADERS, json={
        "transaction_type": "loan",
        "compliance_mode": "traditional",
        "issuer_name": "Auto Compose Co",
        "issuer_type": "Corporate",
        "amount": 2500000,
        "currency": "USD",
        "jurisdictions": ["difc"],
    })
    inst_id = r.json()["id"]

    r = client.post(
        f"/instruments/{inst_id}/documents",
        headers=HEADERS,
        json={"text": LOAN_TEXT, "filename": "t.txt"},
    )
    assert r.status_code == 200, r.text
    result = r.json()
    # DIFC rule fires because no KYC document is attached.
    # The traditional track alone would not flag; composition does.
    assert result["outcome"] == "system_flagged_noncompliant"


def test_submission_override_beats_instrument(client, db):
    _seed_difc_rule(db[0]())

    # Instrument has DIFC, but the submission overrides with [].
    r = client.post("/instruments", headers=HEADERS, json={
        "transaction_type": "loan",
        "compliance_mode": "traditional",
        "issuer_name": "Override Co",
        "issuer_type": "Corporate",
        "amount": 2500000,
        "currency": "USD",
        "jurisdictions": ["difc"],
    })
    inst_id = r.json()["id"]

    r = client.post(
        f"/instruments/{inst_id}/documents",
        headers=HEADERS,
        json={
            "text": LOAN_TEXT,
            "filename": "t.txt",
            "jurisdictions": [],
        },
    )
    assert r.status_code == 200, r.text
    result = r.json()
    # No composition -> traditional track alone -> not_applicable
    assert result["outcome"] == "not_applicable"
