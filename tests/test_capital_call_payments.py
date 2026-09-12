"""Phase C capital-call payment tests -- reconciliation against approved calls:
derived payment status transitions, the approval gate, and the overpayment
refusal. Auth is mocked (the `client` fixture accepts `test-key-123`).
"""
from __future__ import annotations

from app.models.enums import LedgerEntryType

HEADERS = {"X-API-Key": "test-key-123"}


def _make_instrument(client):
    return client.post(
        "/instruments",
        headers=HEADERS,
        json={
            "transaction_type": "private_equity",
            "compliance_mode": "traditional",
            "issuer_name": "Northwind Ventures",
            "issuer_type": "Fund",
            "amount": 10_000_000,
            "currency": "USD",
        },
    )


def _make_investor(client, name="Dana White"):
    return client.post(
        "/investors",
        headers=HEADERS,
        json={"name": name, "investor_type": "institution"},
    )


def _create_call(client, instrument_id, funder_name="Dana White", **overrides):
    payload = {
        "funder_name": funder_name,
        "currency": "USD",
        "capital_owing": 500_000.0,
        "due_date": "2026-12-31T00:00:00",
        "wire_details": "Wire to Northwind Ventures, ABA 021000021",
        "source_text": "Capital Call Notice -- Series A Preferred",
    }
    payload.update(overrides)
    return client.post(
        f"/instruments/{instrument_id}/capital-calls",
        headers=HEADERS,
        json=payload,
    )


def _approve_call(client, call_id):
    """Drive a funder-resolved call through the Phase A gate to APPROVED."""
    return client.post(
        f"/capital-calls/{call_id}/review",
        headers=HEADERS,
        json={"reviewer": "M. Vance", "action": "approve"},
    )


def _record_payment(client, call_id, **overrides):
    payload = {
        "amount": 250_000.0,
        "currency": "USD",
        "paid_date": "2026-09-10T14:30:00",
        "reference": "WIRE-FA-49281",
        "recorded_by": "R. Okafor -- Treasury",
    }
    payload.update(overrides)
    return client.post(
        f"/capital-calls/{call_id}/payments",
        headers=HEADERS,
        json=payload,
    )


# --------------------------------------------------------------------------- #
# Derived status transitions: partial then full
# --------------------------------------------------------------------------- #


def test_partial_then_full_payment_derives_status_transitions(client):
    inst = _make_instrument(client).json()
    _make_investor(client)
    call = _create_call(client, inst["id"]).json()
    assert _approve_call(client, call["id"]).status_code == 200

    # Before any payment: unpaid, full remaining.
    body = [c for c in client.get("/capital-calls", headers=HEADERS).json()
            if c["id"] == call["id"]][0]
    assert body["payment_status"] == "unpaid"
    assert body["total_paid"] == 0.0
    assert body["remaining"] == 500_000.0

    # Partial payment -> partial, remaining halves. Derived, never stored:
    # the call row's own status stays "approved".
    r = _record_payment(client, call["id"])
    assert r.status_code == 201
    payment = r.json()
    assert payment["recorded_by"] == "R. Okafor -- Treasury"
    assert payment["reference"] == "WIRE-FA-49281"

    body = [c for c in client.get("/capital-calls", headers=HEADERS).json()
            if c["id"] == call["id"]][0]
    assert body["payment_status"] == "partial"
    assert body["total_paid"] == 250_000.0
    assert body["remaining"] == 250_000.0
    assert body["status"] == "approved"

    # Full settlement -> paid, remaining 0.
    r = _record_payment(client, call["id"], amount=250_000.0, reference="WIRE-FA-49282")
    assert r.status_code == 201
    body = [c for c in client.get("/capital-calls", headers=HEADERS).json()
            if c["id"] == call["id"]][0]
    assert body["payment_status"] == "paid"
    assert body["total_paid"] == 500_000.0
    assert body["remaining"] == 0.0

    # The payment list reads back both receipts, oldest first.
    listed = client.get(f"/capital-calls/{call['id']}/payments", headers=HEADERS).json()
    assert [p["reference"] for p in listed] == ["WIRE-FA-49281", "WIRE-FA-49282"]


def test_payment_writes_append_only_ledger_entry(client):
    inst = _make_instrument(client).json()
    _make_investor(client)
    call = _create_call(client, inst["id"]).json()
    _approve_call(client, call["id"])
    _record_payment(client, call["id"])

    ledger = client.get(
        f"/instruments/{inst['id']}/ledger", headers=HEADERS
    ).json()
    payment_entries = [
        e for e in ledger
        if e.get("entry_type") == LedgerEntryType.CAPITAL_CALL_PAYMENT.value
    ]
    assert len(payment_entries) == 1
    payload = payment_entries[0]["payload"]
    assert payload["event"] == "capital_call_payment_recorded"
    assert payload["amount"] == 250_000.0
    assert payload["recorded_by"] == "R. Okafor -- Treasury"


# --------------------------------------------------------------------------- #
# The approval gate
# --------------------------------------------------------------------------- #


def test_payment_on_pending_call_is_refused_409(client):
    inst = _make_instrument(client).json()
    _make_investor(client)
    call = _create_call(client, inst["id"]).json()  # PENDING_APPROVAL
    r = _record_payment(client, call["id"])
    assert r.status_code == 409
    assert "not approved" in r.json()["detail"]
    # Nothing was written.
    listed = client.get(f"/capital-calls/{call['id']}/payments", headers=HEADERS)
    assert listed.status_code == 200
    assert listed.json() == []


def test_payment_on_rejected_call_is_refused_409(client):
    inst = _make_instrument(client).json()
    _make_investor(client)
    call = _create_call(client, inst["id"]).json()
    client.post(
        f"/capital-calls/{call['id']}/review",
        headers=HEADERS,
        json={"reviewer": "M. Vance", "action": "reject"},
    )
    r = _record_payment(client, call["id"])
    assert r.status_code == 409


def test_payment_on_unknown_call_404(client):
    r = _record_payment(client, "call-does-not-exist")
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Overpayment refusal -- never silently absorb extra cash
# --------------------------------------------------------------------------- #


def test_overpayment_is_refused_409(client):
    inst = _make_instrument(client).json()
    _make_investor(client)
    call = _create_call(client, inst["id"]).json()
    _approve_call(client, call["id"])
    _record_payment(client, call["id"])  # 250k of 500k

    # Trying to clear the remaining 250k with 250_000.01 is refused.
    r = _record_payment(client, call["id"], amount=250_000.01)
    assert r.status_code == 409
    assert "overpayments are rejected" in r.json()["detail"]

    # The refusal wrote nothing: still one payment, still partial.
    listed = client.get(f"/capital-calls/{call['id']}/payments", headers=HEADERS).json()
    assert len(listed) == 1
    body = [c for c in client.get("/capital-calls", headers=HEADERS).json()
            if c["id"] == call["id"]][0]
    assert body["payment_status"] == "partial"
    assert body["remaining"] == 250_000.0


def test_payment_exactly_at_remaining_is_accepted(client):
    inst = _make_instrument(client).json()
    _make_investor(client)
    call = _create_call(client, inst["id"]).json()
    _approve_call(client, call["id"])
    r = _record_payment(client, call["id"], amount=500_000.0)
    assert r.status_code == 201
    body = [c for c in client.get("/capital-calls", headers=HEADERS).json()
            if c["id"] == call["id"]][0]
    assert body["payment_status"] == "paid"
    assert body["remaining"] == 0.0


# --------------------------------------------------------------------------- #
# Audit-rule and currency guards
# --------------------------------------------------------------------------- #


def test_payment_requires_a_named_recorder_409(client):
    inst = _make_instrument(client).json()
    _make_investor(client)
    call = _create_call(client, inst["id"]).json()
    _approve_call(client, call["id"])
    r = _record_payment(client, call["id"], recorded_by="   ")
    assert r.status_code == 409
    assert "named recorder" in r.json()["detail"]


def test_payment_currency_must_match_the_call_409(client):
    inst = _make_instrument(client).json()
    _make_investor(client)
    call = _create_call(client, inst["id"]).json()
    _approve_call(client, call["id"])
    r = _record_payment(client, call["id"], currency="EUR", amount=100_000.0)
    assert r.status_code == 409
    assert "does not match" in r.json()["detail"]
