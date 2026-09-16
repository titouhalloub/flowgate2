"""Phase 3.6 — SAFE extraction produces a CREATE_CONVERTIBLE proposal,
and approval creates the Convertible row. Never auto-creates."""

from app.models.enums import DocumentType, ProposalType


SAFE_TEXT = """
SIMPLE AGREEMENT FOR FUTURE EQUITY

Acme Robotics Inc. (the "Company")
Horizon Ventures LLC (the "Investor")

In exchange for the payment by the Investor of $500,000 (the "Purchase Amount"),
the Company hereby issues to the Investor the right to certain shares of the
Company's Capital Stock, on the terms set forth below.

Post-Money Valuation Cap: $10,000,000
Discount Rate: 20%

The Investor shall have pro-rata rights.

Upon an Equity Financing, this SAFE converts into shares of Preferred Stock.
"""

def _create_instrument(client, issuer="Acme Robotics Inc."):
    r = client.post("/instruments", json={
        "transaction_type": "equity",
        "compliance_mode": "traditional",
        "issuer_name": issuer,
        "issuer_type": "Corporate",
        "amount": 500000,
        "currency": "USD",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_safe_document_creates_proposal(client):
    inst_id = _create_instrument(client)
    r = client.post(f"/instruments/{inst_id}/documents", json={
        "text": SAFE_TEXT, "filename": "acme_safe.txt",
    })
    assert r.status_code == 200, r.text
    assert r.json()["document"]["document_type"] == DocumentType.SAFE.value

    proposals = client.get("/cap-table-proposals").json()
    matching = [p for p in proposals if p["proposal_type"] == ProposalType.CREATE_CONVERTIBLE.value]
    assert len(matching) == 1
    assert matching[0]["payload"]["investor_name"] == "Horizon Ventures LLC"


def test_approval_creates_convertible(client):
    inst_id = _create_instrument(client)
    client.post(f"/instruments/{inst_id}/documents", json={
        "text": SAFE_TEXT, "filename": "acme_safe.txt",
    })
    proposals = client.get("/cap-table-proposals").json()
    pid = [p for p in proposals if p["proposal_type"] == ProposalType.CREATE_CONVERTIBLE.value][0]["id"]

    r = client.post(f"/cap-table-proposals/{pid}/approve?reviewer=Sarah%20Jenkins")
    assert r.status_code == 200, r.text

    convertibles = client.get("/convertibles/Acme Robotics Inc.").json()
    assert len(convertibles) == 1
    assert convertibles[0]["investor_name"] == "Horizon Ventures LLC"
    assert convertibles[0]["document_id"] is not None


def test_rejection_does_not_create_convertible(client):
    inst_id = _create_instrument(client)
    client.post(f"/instruments/{inst_id}/documents", json={
        "text": SAFE_TEXT, "filename": "acme_safe.txt",
    })
    proposals = client.get("/cap-table-proposals").json()
    pid = [p for p in proposals if p["proposal_type"] == ProposalType.CREATE_CONVERTIBLE.value][0]["id"]

    r = client.post(f"/cap-table-proposals/{pid}/reject?reviewer=Sarah%20Jenkins")
    assert r.status_code == 200, r.text

    convertibles = client.get("/convertibles/Acme Robotics Inc.").json()
    assert len(convertibles) == 0


def test_two_uploads_create_two_proposals(client):
    """Each upload creates a new Document; each Document gets its own
    proposal. This is correct — the idempotency guard is per-document,
    not per-text."""
    inst_id = _create_instrument(client)
    for _ in range(2):
        client.post(f"/instruments/{inst_id}/documents", json={
            "text": SAFE_TEXT, "filename": "acme_safe.txt",
        })

    proposals = client.get("/cap-table-proposals").json()
    matching = [p for p in proposals if p["proposal_type"] == ProposalType.CREATE_CONVERTIBLE.value]
    assert len(matching) == 2
