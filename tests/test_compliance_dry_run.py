"""POST /compliance/dry-run-grant -- read-only grant verification (Phase 1)."""
from datetime import datetime, timedelta, timezone

import pytest

from app.auth import AuthUser
from app.main import app, require_api_key

HEADERS = {"X-API-Key": "test-key-123"}
FMV = 2.50


def _dt(**kwargs) -> datetime:
    return datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(**kwargs)


@pytest.fixture()
def client2(client):
    """The shared `client` fixture overrides ``require_api_key`` with a bare
    string, which breaks ``require_role``-guarded seed routes. Override it
    with a real AuthUser so the role-gated POSTs work."""
    app.dependency_overrides[require_api_key] = lambda: AuthUser(
        id="dry-admin", email="dry@example.com", role="admin",
        auth_method="clerk", external_auth_id="dry-admin",
    )
    return client


def _post_valuation(client, issuer: str, price: float, when: datetime) -> None:
    r = client.post("/valuations", headers=HEADERS, json={
        "issuer_name": issuer, "valuation_date": when.isoformat(),
        "price_per_share": price, "valuation_type": "fmv_409a",
        "method": None, "notes": None,
    })
    assert r.status_code == 201, r.text


def _security(client, issuer: str, name: str, sec_type: str) -> str:
    r = client.post("/securities", headers=HEADERS, json={
        "issuer_name": issuer, "name": name, "security_type": sec_type,
        "authorized_shares": 1_000_000,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _investor(client, name: str) -> str:
    r = client.post("/investors", headers=HEADERS,
                    json={"name": name, "investor_type": "individual"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _setup(client, sec_type: str = "option", fmv: float | None = FMV):
    issuer = "DryRun Co"
    if fmv is not None:
        _post_valuation(client, issuer, fmv, _dt(days=0))
    return (issuer,
            _security(client, issuer, "Shares", sec_type),
            _investor(client, "grantee"))


def _dry(client, issuer, security_id, holder_id, price, qty=10_000):
    return client.post("/compliance/dry-run-grant", headers=HEADERS, json={
        "issuer_name": issuer, "holder_id": holder_id,
        "security_id": security_id, "quantity": qty,
        "price_per_share": price, "event_type": "issuance",
    })


# --------------------------------------------------------------------------
# Gate behaviour
# --------------------------------------------------------------------------

def test_compliant_option_grant(client2):
    issuer, sec, holder = _setup(client2, "option", FMV)
    r = _dry(client2, issuer, sec, holder, FMV)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["compliant"] is True
    assert b["would_be_recorded"] is True
    assert b["rejection_reason"] is None
    assert b["current_fmv"] == FMV
    assert b["fmv_effective_date"] is not None


def test_below_fmv_option_rejected(client2):
    issuer, sec, holder = _setup(client2, "option", FMV)
    r = _dry(client2, issuer, sec, holder, 1.00)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["compliant"] is False
    assert b["would_be_recorded"] is False
    assert "409A" in b["rejection_reason"]
    assert b["current_fmv"] == FMV


def test_common_below_fmv_allowed(client2):
    """Common stock is an issuance price, not an exercise price -- never gated."""
    issuer, sec, holder = _setup(client2, "common", FMV)
    r = _dry(client2, issuer, sec, holder, 1.00)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["compliant"] is True
    assert b["rejection_reason"] is None


def test_no_fmv_on_file_is_compliant(client2):
    """Nothing to violate when no 409A exists -- matches the route."""
    issuer, sec, holder = _setup(client2, "option", fmv=None)
    r = _dry(client2, issuer, sec, holder, 0.01)
    b = r.json()
    assert b["compliant"] is True
    assert b["current_fmv"] is None
    assert b["fmv_effective_date"] is None


# --------------------------------------------------------------------------
# Read-only guarantee
# --------------------------------------------------------------------------

def test_does_not_write_to_ledger(client2):
    issuer, sec, holder = _setup(client2, "option", FMV)
    url = f"/cap-table/{issuer.replace(' ', '%20')}"
    before = client2.get(url).json()
    n_before = len(before["positions"])

    assert _dry(client2, issuer, sec, holder, 1.00).status_code == 200   # rejected
    assert _dry(client2, issuer, sec, holder, FMV).status_code == 200    # allowed

    after = client2.get(url).json()
    assert len(after["positions"]) == n_before, "dry-run must not record an event"
    assert (after["total_fully_diluted_shares"]
            == before["total_fully_diluted_shares"])


# --------------------------------------------------------------------------
# Phase 1 contract
# --------------------------------------------------------------------------

def test_returns_empty_rule_evaluations(client2):
    """Phase 1 ships the 409A gate only. The field exists so MCP clients do not
    change shape when the grant-rule engine lands in Phase 2."""
    issuer, sec, holder = _setup(client2, "option", FMV)
    b = _dry(client2, issuer, sec, holder, FMV).json()
    assert isinstance(b["rule_evaluations"], list)
    assert b["rule_evaluations"] == []


def test_evaluated_at_and_staleness_present(client2):
    issuer, sec, holder = _setup(client2, "option", FMV)
    b = _dry(client2, issuer, sec, holder, FMV).json()
    assert "evaluated_at" in b
    assert isinstance(b["fmv_stale"], bool)


# --------------------------------------------------------------------------
# Refactor is behaviour-preserving
# --------------------------------------------------------------------------

def test_returns_same_message_as_route(client2):
    """The dry-run rejection must be byte-identical to what POST
    /cap-table-events would have raised for the same grant."""
    issuer, sec, holder = _setup(client2, "option", FMV)

    dry = _dry(client2, issuer, sec, holder, 1.00).json()
    assert dry["compliant"] is False

    write = client2.post("/cap-table-events", headers=HEADERS, json={
        "security_id": sec, "event_type": "issuance", "holder_id": holder,
        "quantity": 10_000, "price_per_share": 1.00,
        "effective_date": datetime.now(timezone.utc).isoformat(),
    })
    assert write.status_code == 400, write.text
    assert write.json()["detail"] == dry["rejection_reason"]


# --------------------------------------------------------------------------
# Validation / auth
# --------------------------------------------------------------------------

def test_requires_auth(client2):
    app.dependency_overrides.pop(require_api_key, None)
    r = client2.post("/compliance/dry-run-grant", json={
        "issuer_name": "X", "holder_id": "h", "security_id": "s",
        "quantity": 1, "price_per_share": 1.0, "event_type": "issuance",
    })
    assert r.status_code == 401


def test_invalid_event_type_returns_422(client2):
    issuer, sec, holder = _setup(client2, "option", FMV)
    r = client2.post("/compliance/dry-run-grant", headers=HEADERS, json={
        "issuer_name": issuer, "holder_id": holder, "security_id": sec,
        "quantity": 1, "price_per_share": 1.0, "event_type": "foobar",
    })
    assert r.status_code == 422, r.text


def test_negative_quantity_returns_422(client2):
    issuer, sec, holder = _setup(client2, "option", FMV)
    r = _dry(client2, issuer, sec, holder, FMV, qty=-1)
    assert r.status_code == 422, r.text


def test_unknown_security_returns_404(client2):
    issuer, _sec, holder = _setup(client2, "option", FMV)
    r = _dry(client2, issuer, "no-such-security", holder, FMV)
    assert r.status_code == 404, r.text
