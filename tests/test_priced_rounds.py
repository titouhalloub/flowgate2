"""Phase 3.5 acceptance: atomic priced-round commit.

Covers plan Tests 5 (atomicity), 8 (idempotency), 9 (status transitions),
10 (ledger completeness), plus the interaction boundaries: converted shares
land fully vested on the cap table, and conversion is never 409A-gated.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_session
from app.main import app, require_api_key
from app.models.orm import LedgerEntry


@pytest.fixture()
def client_db(tmp_path):
    """TestClient plus a handle on the same scratch SessionLocal, so ledger
    rows can be asserted directly (there is no ledger read endpoint)."""
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _override_session():
        with SessionLocal() as s:
            yield s

    def _override_auth(key=None):
        return "test-key-123"

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_api_key] = _override_auth
    try:
        with TestClient(app) as c:
            yield c, SessionLocal
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def _safe(client: TestClient, issuer: str = "Round Co", investor: str = "YC Fund",
          kind: str = "post_money_safe", amount: float = 1_000_000.0,
          cap: float = 20_000_000.0, discount: float | None = 0.20) -> dict:
    resp = client.post("/convertibles", json={
        "issuer_name": issuer, "investor_name": investor,
        "purchase_amount": amount, "instrument_kind": kind,
        "valuation_cap": cap, "discount_rate": discount,
        "issued_date": "2026-01-15",
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def _commit(client: TestClient, issuer: str = "Round Co", crid: str | None = None,
            round_name: str = "Series A", price: float = 1.00,
            round_shares: int = 10_000_000, pre: int = 40_000_000,
            pool: int = 5_000_000):
    return client.post("/priced-rounds", json={
        "issuer_name": issuer, "round_name": round_name,
        "price_per_share": price, "round_shares": round_shares,
        "pre_safe_shares": pre, "options_pool": pool,
        "effective_date": "2026-06-01", "reviewer": "Dana Legal VP",
        "client_request_id": crid or str(uuid.uuid4()),
    })


def test_commit_happy_path(client_db):
    client, _ = client_db
    conv = _safe(client)
    resp = _commit(client)
    assert resp.status_code == 201, resp.text
    body = resp.json()

    # Round math: post-money total = pre_safe + pool + round + conversions
    assert body["post_money_shares"] == 40_000_000 + 5_000_000 + 10_000_000 + 2_368_421
    assert body["issuance_event_id"]
    assert body["total_conversion_shares"] == pytest.approx(2_368_421.05, rel=1e-6)

    c = body["conversions"][0]
    assert c["convertible_id"] == conv["id"]
    assert c["investor_name"] == "YC Fund"
    assert c["pricing_basis"] == "cap"
    assert c["shares_issued"] == pytest.approx(2_368_421.05, rel=1e-6)
    assert c["conversion_price"] == pytest.approx(0.42222, rel=1e-4)

    # The convertible flipped to CONVERTED and points at its event.
    row = client.get("/convertibles/Round%20Co").json()[0]
    assert row["status"] == "converted"
    assert row["converted_at"] is not None
    assert row["conversion_event_id"] == c["event_id"]

    # The round is readable via the list endpoint.
    rounds = client.get("/priced-rounds/Round%20Co").json()
    assert len(rounds) == 1
    assert rounds[0]["id"] == body["id"]


def test_commit_cap_table_fully_vested(client_db):
    """Plan Test 7 (pulled forward): converted shares land on the cap table
    fully vested -- vested == shares, unvested == 0 for every new position."""
    client, _ = client_db
    _safe(client)
    _commit(client)
    cap = client.get("/cap-table/Round%20Co").json()
    assert cap["positions"], "no positions after commit"
    for pos in cap["positions"]:
        assert pos["vested_shares"] == pytest.approx(pos["shares"])
        assert pos["unvested_shares"] == 0
    names = {p["security_name"] for p in cap["positions"]}
    assert names == {"Series A Preferred"}


def test_commit_atomicity_pre_money_rejected(client_db):
    """Plan Test 5: a pre-money SAFE poisons the whole commit -- nothing
    is written."""
    client, _ = client_db
    _safe(client, investor="Post Fund")
    _safe(client, investor="Pre Fund", kind="pre_money_safe")

    resp = _commit(client)
    assert resp.status_code == 400
    assert "Pre-money" in resp.json()["detail"]

    # Nothing persisted: no round, no conversion, statuses untouched.
    assert client.get("/priced-rounds/Round%20Co").json() == []
    rows = client.get("/convertibles/Round%20Co").json()
    assert {r["status"] for r in rows} == {"outstanding"}
    assert all(r["conversion_event_id"] is None for r in rows)
    cap = client.get("/cap-table/Round%20Co").json()
    assert cap["positions"] == []


def test_commit_idempotent_same_request_id(client_db):
    """Plan Test 8: a retried commit returns the original round and writes
    nothing new."""
    client, _ = client_db
    _safe(client)
    crid = str(uuid.uuid4())
    first = _commit(client, crid=crid)
    assert first.status_code == 201
    body1 = first.json()

    second = _commit(client, crid=crid)
    assert second.status_code == 200
    body2 = second.json()
    assert body2["id"] == body1["id"]
    assert body2["issuance_event_id"] == body1["issuance_event_id"]
    assert body2["conversions"] == body1["conversions"]

    # Still exactly one round; the convertible's event link is unchanged.
    assert len(client.get("/priced-rounds/Round%20Co").json()) == 1
    row = client.get("/convertibles/Round%20Co").json()[0]
    assert row["conversion_event_id"] == body1["conversions"][0]["event_id"]


def test_converted_safe_not_reconverted(client_db):
    """Plan Test 9: a later round must not touch already-converted SAFEs."""
    client, _ = client_db
    _safe(client)
    first = _commit(client).json()
    event_id_1 = first["conversions"][0]["event_id"]

    second = _commit(client, round_name="Series B", price=2.00,
                     round_shares=5_000_000)
    assert second.status_code == 201
    body2 = second.json()
    assert body2["conversions"] == []
    assert body2["total_conversion_shares"] == 0
    assert body2["post_money_shares"] == 40_000_000 + 5_000_000 + 5_000_000

    row = client.get("/convertibles/Round%20Co").json()[0]
    assert row["conversion_event_id"] == event_id_1  # untouched by round 2


def test_ledger_entries_share_round_id(client_db):
    """Plan Test 10: one ledger entry per conversion + one for the round,
    all linked by the same round_id."""
    client, SessionLocal = client_db
    _safe(client, investor="Fund One")
    _safe(client, investor="Fund Two")
    body = _commit(client).json()

    with SessionLocal() as s:
        entries = [
            e for e in s.query(LedgerEntry).all()
            if isinstance(e.payload, dict) and e.payload.get("round_id") == body["id"]
        ]
    assert len(entries) == 3  # 1 round issuance + 2 conversions
    kinds = {e.payload["kind"] for e in entries}
    assert kinds == {"priced_round_issuance", "safe_conversion"}
    assert all(e.payload["reviewer"] == "Dana Legal VP" for e in entries)


def test_conversion_bypasses_409a_gate(client_db):
    """Plan Test 6 (pulled forward): conversion issues preferred stock, so a
    conversion price far below the recorded 409A FMV is not a violation."""
    client, _ = client_db
    _safe(client)
    vresp = client.post("/valuations", json={
        "issuer_name": "Round Co", "valuation_date": "2026-05-01T00:00:00Z",
        "price_per_share": 2.50, "valuation_type": "fmv_409a",
    })
    assert vresp.status_code == 201, vresp.text

    resp = _commit(client)  # conversion price ~$0.42 << $2.50 FMV
    assert resp.status_code == 201, resp.text
    assert resp.json()["conversions"][0]["pricing_basis"] == "cap"
