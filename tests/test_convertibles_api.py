"""Phase 3.4 acceptance: convertible CRUD + priced-round preview over HTTP.

The pure math lives in app.captable.compute_conversions and is covered by
tests/test_conversion_math.py; here we verify the HTTP layer wires it up
correctly -- auth, validation, status filtering, and the end-to-end
preview numbers from the plan (cap-basis and discount-basis cases).
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient


def _create_safe(client: TestClient, issuer: str = "Preview Co", expect: int = 201,
                 **overrides) -> dict:
    body = {
        "issuer_name": issuer,
        "investor_name": "YC Post-Money Fund",
        "purchase_amount": 1_000_000.0,
        "instrument_kind": "post_money_safe",
        "valuation_cap": 20_000_000.0,
        "discount_rate": 0.20,
        "issued_date": "2026-01-15",
    }
    body.update(overrides)
    resp = client.post("/convertibles", json=body)
    assert resp.status_code == expect, resp.text
    return resp.json()


def test_create_and_list_convertibles(client: TestClient):
    row = _create_safe(client)
    assert row["status"] == "outstanding"
    assert row["converted_at"] is None
    assert row["conversion_event_id"] is None
    assert row["purchase_amount"] == 1_000_000.0

    listed = client.get("/convertibles/Preview%20Co")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    # Status filter narrows; other issuers stay separate.
    assert len(client.get("/convertibles/Preview%20Co?status=outstanding").json()) == 1
    assert client.get("/convertibles/Preview%20Co?status=converted").json() == []
    assert client.get("/convertibles/No%20Such%20Co").json() == []


def test_create_rejects_bad_input(client: TestClient):
    # Negative purchase amount (schema gt=0).
    _create_safe(client, purchase_amount=-5, expect=422)

    # Unknown instrument kind (pattern).
    _create_safe(client, instrument_kind="kitten_bond", expect=422)

    # The rejections wrote nothing.
    assert client.get("/convertibles/Preview%20Co").json() == []


def test_preview_cap_basis_end_to_end(client: TestClient):
    """Plan Test 1 over HTTP: $1M at $20M cap, 20% discount, round $1.00,
    40M pre-safe shares + 5M pool -> cap basis wins at $0.4222/sh."""
    _create_safe(client)
    resp = client.post("/priced-rounds/preview", json={
        "issuer_name": "Preview Co",
        "round_price": 1.00,
        "pre_safe_shares": 40_000_000,
        "options_pool": 5_000_000,
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_new_shares"] > 0

    conv = body["conversions"][0]
    assert conv["pricing_basis"] == "cap"
    # JSON round-trip perturbs the float tail; compare with tolerance.
    assert conv["shares_issued"] == pytest.approx(2_368_421.0526315789, rel=1e-9)
    assert conv["cap_price"] == pytest.approx(0.4222222222222222, rel=1e-9)
    assert conv["discount_price"] == pytest.approx(0.80, rel=1e-9)
    assert conv["conversion_price"] == pytest.approx(conv["cap_price"], rel=1e-12)


def test_preview_discount_basis_end_to_end(client: TestClient):
    """Plan Test 2 over HTTP: round price $0.20 -> discount price $0.16
    beats the $0.4222 cap price -> 6,250,000 shares."""
    _create_safe(client)
    resp = client.post("/priced-rounds/preview", json={
        "issuer_name": "Preview Co",
        "round_price": 0.20,
        "pre_safe_shares": 40_000_000,
        "options_pool": 5_000_000,
    })
    assert resp.status_code == 200, resp.text
    conv = resp.json()["conversions"][0]
    assert conv["pricing_basis"] == "discount"
    assert conv["shares_issued"] == pytest.approx(6_250_000.0, rel=1e-9)
    assert conv["conversion_price"] == pytest.approx(0.16, rel=1e-9)


def test_preview_pre_money_safe_rejected_over_http(client: TestClient):
    """Recorded but never converted: the preview must 400 on pre-money."""
    _create_safe(client, investor_name="Old-School Investor",
                 instrument_kind="pre_money_safe")
    resp = client.post("/priced-rounds/preview", json={
        "issuer_name": "Preview Co",
        "round_price": 1.00,
        "pre_safe_shares": 40_000_000,
        "options_pool": 5_000_000,
    })
    assert resp.status_code == 400
    assert "Pre-money" in resp.json()["detail"]


def test_preview_with_no_convertibles_is_empty_not_error(client: TestClient):
    resp = client.post("/priced-rounds/preview", json={
        "issuer_name": "Empty Co",
        "round_price": 1.00,
        "pre_safe_shares": 10_000_000,
        "options_pool": 0,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["conversions"] == []
    assert body["total_new_shares"] == 0
