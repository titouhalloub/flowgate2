"""Cap table history endpoint: month-end snapshots from event replay."""
import calendar
from datetime import datetime, timedelta, timezone

import pytest

from app.auth import AuthUser
from app.main import app, require_api_key

HEADERS = {"X-API-Key": "test-key-123"}


@pytest.fixture()
def hist_client(client):
    """The shared `client` fixture overrides ``require_api_key`` with the bare
    string "test-key-123". Routes guarded by ``require_role`` dereference
    ``user.role`` on that value and blow up, so seeding via HTTP needs a real
    AuthUser instead."""
    app.dependency_overrides[require_api_key] = lambda: AuthUser(
        id="hist-admin",
        email="hist-admin@example.com",
        role="admin",
        auth_method="clerk",
        external_auth_id="hist-admin",
    )
    return client


def _seed_issuer(client, issuer="HistCo Inc.") -> str:
    r = client.post("/securities", headers=HEADERS, json={
        "issuer_name": issuer,
        "name": "Common Stock",
        "security_type": "common",
        "authorized_shares": 10_000_000,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _seed_investor(client, name: str) -> str:
    r = client.post("/investors", headers=HEADERS, json={
        "name": name, "investor_type": "individual",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _issue(client, security_id, holder_id, quantity, days_ago=0):
    when = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    r = client.post("/cap-table-events", headers=HEADERS, json={
        "security_id": security_id,
        "event_type": "issuance",
        "holder_id": holder_id,
        "quantity": quantity,
        "effective_date": when,
    })
    assert r.status_code == 201, r.text


def _history(client, issuer="HistCo Inc.", **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"/cap-table/{issuer}/history" + (f"?{q}" if q else "")
    return client.get(url, headers=HEADERS)


# --------------------------------------------------------------------------
# Empty / unknown issuer
# --------------------------------------------------------------------------

def test_empty_history_for_unknown_issuer(hist_client):
    """Decision 1: unknown issuer is 200 with an empty series, not 404 --
    matching GET /cap-table/{issuer_name}."""
    r = _history(hist_client, issuer="Does Not Exist")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["issuer_name"] == "Does Not Exist"
    assert body["snapshots"] == []


def test_history_with_no_events(hist_client):
    """Issuer exists but has never been issued: 200, empty series."""
    _seed_issuer(hist_client)
    r = _history(hist_client)
    assert r.status_code == 200, r.text
    assert r.json()["snapshots"] == []


# --------------------------------------------------------------------------
# Replay correctness
# --------------------------------------------------------------------------

def test_history_after_single_issuance(hist_client):
    """One issuance ~3 months back: earlier snapshots are 0, later ones carry
    the shares."""
    sec = _seed_issuer(hist_client)
    holder = _seed_investor(hist_client, "Hist Founder")
    _issue(hist_client, sec, holder, 1_000_000, days_ago=92)

    r = _history(hist_client, months=6)
    assert r.status_code == 200, r.text
    snaps = r.json()["snapshots"]
    assert len(snaps) == 6

    issued = (datetime.now(timezone.utc) - timedelta(days=92)).date()
    before = [s for s in snaps if datetime.fromisoformat(s["date"]).date() < issued]
    after = [s for s in snaps if datetime.fromisoformat(s["date"]).date() >= issued]
    assert before, "expected at least one snapshot before the issuance"
    assert after, "expected at least one snapshot at/after the issuance"
    for s in before:
        assert s["total_fully_diluted_shares"] == 0
        assert s["top_holders"] == []
    for s in after:
        assert s["total_fully_diluted_shares"] == 1_000_000
        assert s["holder_count"] == 1
        assert s["top_holders"][0]["shares"] == 1_000_000
        assert s["top_holders"][0]["holder_name"] == "Hist Founder"


def test_history_top_holders_stable(hist_client):
    """Eight holders: exactly six get their own series, the other two are
    summed into other_holders_total, and the top set never changes."""
    sec = _seed_issuer(hist_client)
    sizes = [100, 90, 80, 70, 60, 50, 40, 30]  # unequal, so "top" is clear
    for i, qty in enumerate(sizes):
        _issue(hist_client, sec, _seed_investor(hist_client, f"H{i}"), qty, days_ago=200)

    r = _history(hist_client, months=6)
    assert r.status_code == 200, r.text
    snaps = r.json()["snapshots"]
    assert snaps

    total = sum(sizes)
    for s in snaps:
        assert len(s["top_holders"]) == 6, "top_holders must cap at six"
        assert s["holder_count"] == 8
        assert s["total_fully_diluted_shares"] == total
        breakdown = (
            sum(h["shares"] for h in s["top_holders"]) + s["other_holders_total"]
        )
        assert breakdown == total, "top six + remainder must equal the total"

    ids = {tuple(h["holder_id"] for h in s["top_holders"]) for s in snaps}
    assert len(ids) == 1, "top-holder set must be stable across snapshots"


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def test_history_rejects_invalid_months(hist_client):
    for bad in (0, 100, -3):
        r = _history(hist_client, months=bad)
        assert r.status_code == 400, f"months={bad} -> {r.status_code}"
        assert "months" in r.json()["detail"]


def test_history_rejects_invalid_interval(hist_client):
    r = _history(hist_client, interval="hourly")
    assert r.status_code == 400
    assert "interval" in r.json()["detail"]


def test_history_default_is_6_months(hist_client):
    sec = _seed_issuer(hist_client)
    _issue(hist_client, sec, _seed_investor(hist_client, "Default Holder"), 1000,
           days_ago=200)

    r = _history(hist_client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["interval"] == "monthly"
    assert len(body["snapshots"]) == 6


def test_history_monthly_boundaries(hist_client):
    sec = _seed_issuer(hist_client)
    _issue(hist_client, sec, _seed_investor(hist_client, "Boundary Holder"), 1000,
           days_ago=200)

    r = _history(hist_client, months=6)
    snaps = r.json()["snapshots"]
    assert len(snaps) == 6
    for s in snaps:
        d = datetime.fromisoformat(s["date"])
        assert d.day == calendar.monthrange(d.year, d.month)[1], (
            f"{s['date']} is not a month-end"
        )


def test_history_accepts_weekly_interval(hist_client):
    sec = _seed_issuer(hist_client)
    _issue(hist_client, sec, _seed_investor(hist_client, "Weekly Holder"), 1000,
           days_ago=200)

    r = _history(hist_client, months=3, interval="weekly")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["interval"] == "weekly"
    assert len(body["snapshots"]) == 12  # 3 months * 4 weeks
    for s in body["snapshots"]:
        assert datetime.fromisoformat(s["date"]).weekday() == 6  # Sunday


def test_history_requires_auth(client):
    """With the auth override removed the gate must reject the call."""
    app.dependency_overrides.pop(require_api_key, None)
    r = client.get("/cap-table/HistCo Inc./history")
    assert r.status_code == 401
