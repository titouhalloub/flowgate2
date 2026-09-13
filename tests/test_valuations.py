"""Tests for 409A valuations: record-keeping, latest/type filtering, the
staleness nag, and the below-FMV option-grant compliance gate.

Spec: CAPTABLE-ROADMAP-FEATURES.md Feature 2.
"""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient


def _dt(**kwargs) -> datetime:
    return datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(**kwargs)


def _post_valuation(client: TestClient, issuer: str, price: float, when: datetime,
                    vtype: str = "fmv_409a", method: str | None = None) -> dict:
    resp = client.post("/valuations", json={
        "issuer_name": issuer,
        "valuation_date": when.isoformat(),
        "price_per_share": price,
        "valuation_type": vtype,
        "method": method,
        "notes": None,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def _make_security(client: TestClient, issuer: str, name: str, sec_type: str) -> str:
    resp = client.post("/securities", json={
        "issuer_name": issuer, "name": name, "security_type": sec_type,
        "authorized_shares": 1_000_000,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _make_investor(client: TestClient, name: str) -> str:
    resp = client.post("/investors", json={"name": name, "investor_type": "individual"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _issue(client: TestClient, security_id: str, holder_id: str, qty: float,
           price: float | None, when: datetime):
    return client.post("/cap-table-events", json={
        "security_id": security_id,
        "event_type": "issuance",
        "holder_id": holder_id,
        "quantity": qty,
        "price_per_share": price,
        "effective_date": when.isoformat(),
    })


# --------------------------------------------------------------------------- #
# Test 1: Record + retrieve history (newest first) with type filter
# --------------------------------------------------------------------------- #


def test_record_and_retrieve_history(client: TestClient):
    _post_valuation(client, "Forty Nine A Inc", 1.50, _dt(days=0))
    _post_valuation(client, "Forty Nine A Inc", 2.25, _dt(days=200))
    round_row = _post_valuation(
        client, "Forty Nine A Inc", 3.00, _dt(days=300),
        vtype="preferred_price_round", method="Series A price",
    )
    assert round_row["valuation_type"] == "preferred_price_round"
    assert round_row["method"] == "Series A price"

    history = client.get("/valuations/Forty%20Nine%20A%20Inc")
    assert history.status_code == 200
    rows = history.json()
    assert [r["price_per_share"] for r in rows] == [3.00, 2.25, 1.50]

    # Type filter only narrows -- never reorders.
    fmv_only = client.get("/valuations/Forty%20Nine%20A%20Inc?valuation_type=fmv_409a")
    assert [r["price_per_share"] for r in fmv_only.json()] == [2.25, 1.50]

    # Unknown issuer -> empty history, latest -> 404.
    assert client.get("/valuations/No%20Such%20Co").json() == []
    assert client.get("/valuations/No%20Such%20Co/latest").status_code == 404


# --------------------------------------------------------------------------- #
# Test 2: Latest with staleness nag (12 months, warning only)
# --------------------------------------------------------------------------- #


def test_latest_staleness_nag(client: TestClient):
    _post_valuation(client, "Stale Co", 2.00, datetime.now(timezone.utc) - timedelta(days=400))
    fresh = _post_valuation(client, "Fresh Co", 4.00, datetime.now(timezone.utc) - timedelta(days=30))

    stale = client.get("/valuations/Stale%20Co/latest")
    assert stale.status_code == 200
    body = stale.json()
    assert body["is_stale"] is True
    assert body["months_old"] > 12

    latest = client.get("/valuations/Fresh%20Co/latest")
    body = latest.json()
    assert body["is_stale"] is False
    assert body["months_old"] < 12
    assert body["price_per_share"] == fresh["price_per_share"]

    # Explicit as_of works for point-in-time reads.
    old_read = client.get(
        "/valuations/Stale%20Co/latest",
        params={"as_of": (datetime(2024, 3, 1, tzinfo=timezone.utc)).isoformat()},
    )
    # Valuation is dated ~now, i.e. AFTER the as_of ref -> not on file yet.
    assert old_read.status_code == 404


# --------------------------------------------------------------------------- #
# Test 3: Option issued below the 409A FMV -> rejected; at FMV -> allowed
# --------------------------------------------------------------------------- #


def test_option_below_fmv_rejected(client: TestClient):
    issuer = "Compliance Co"
    _post_valuation(client, issuer, 2.00, _dt(days=0))  # FMV $2.00
    opt = _make_security(client, issuer, "Options", "option")
    holder = _make_investor(client, "grantee")

    # Below FMV -> hard reject.
    below = _issue(client, opt, holder, 10_000, 1.00, _dt(days=90))
    assert below.status_code == 400, below.text
    assert "409A" in below.json()["detail"]

    # The rejected event must not linger in the log.
    cap = client.get("/cap-table/Compliance%20Co")
    assert cap.json()["positions"] == []

    # At FMV -> allowed.
    at_fmv = _issue(client, opt, holder, 10_000, 2.00, _dt(days=90))
    assert at_fmv.status_code == 201, at_fmv.text

    # Above FMV -> allowed.
    above = _issue(client, opt, holder, 5_000, 2.50, _dt(days=91))
    assert above.status_code == 201, above.text


# --------------------------------------------------------------------------- #
# Test 4: Grant dated before the first 409A -> allowed (nothing to violate)
# --------------------------------------------------------------------------- #


def test_grant_before_first_fmv_allowed(client: TestClient):
    issuer = "Early Days Inc"
    _post_valuation(client, issuer, 2.00, _dt(days=180))
    opt = _make_security(client, issuer, "Options", "option")
    holder = _make_investor(client, "early-employee")

    resp = _issue(client, opt, holder, 10_000, 0.50, _dt(days=0))
    assert resp.status_code == 201, resp.text


# --------------------------------------------------------------------------- #
# Test 5: Common stock priced below FMV -> allowed (strike rule is options only)
# --------------------------------------------------------------------------- #


def test_common_below_fmv_allowed(client: TestClient):
    issuer = "Common Co"
    _post_valuation(client, issuer, 2.00, _dt(days=0))
    common = _make_security(client, issuer, "Common", "common")
    holder = _make_investor(client, "founder")

    resp = _issue(client, common, holder, 100_000, 0.01, _dt(days=30))
    assert resp.status_code == 201, resp.text


# --------------------------------------------------------------------------- #
# Test 6: Cap table surfaces 409A context (price, date, staleness)
# --------------------------------------------------------------------------- #


def test_cap_table_409a_context(client: TestClient):
    issuer = "Context Co"
    _post_valuation(client, issuer, 1.00, _dt(days=0))

    cap = client.get("/cap-table/Context%20Co", params={"as_of": _dt(days=30).isoformat()})
    assert cap.status_code == 200
    body = cap.json()
    assert body["latest_409a_price"] == 1.00
    assert body["latest_409a_date"].startswith("2024-01-01")
    assert body["latest_409a_stale"] is False

    # A snapshot more than 12 months after the valuation flags staleness.
    old_cap = client.get("/cap-table/Context%20Co", params={"as_of": _dt(days=500).isoformat()})
    assert old_cap.json()["latest_409a_stale"] is True

    # Point-in-time: as_of BEFORE the valuation -> no FMV in effect yet.
    early = client.get("/cap-table/Context%20Co", params={"as_of": _dt(days=-30).isoformat()})
    assert early.json()["latest_409a_price"] is None

    # An issuer with no valuations carries no context at all.
    opt = _make_security(client, "Bare Co", "Options", "option")
    assert opt
    bare = client.get("/cap-table/Bare%20Co")
    assert bare.json()["latest_409a_price"] is None
    assert bare.json()["latest_409a_stale"] is False
