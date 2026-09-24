# Tests for GET /issuers.
from __future__ import annotations

HEADERS = {"X-API-Key": "test-key-123"}


def _make_instrument(client, issuer_name):
    return client.post(
        "/instruments",
        headers=HEADERS,
        json={
            "transaction_type": "equity",
            "compliance_mode": "traditional",
            "issuer_name": issuer_name,
            "issuer_type": "Corporate",
            "amount": 1000000.0,
            "currency": "USD",
        },
    )


def test_list_issuers_empty_initially(client):
    # The conftest fixture resets the DB per test, so no instruments
    # exist at this point.
    r = client.get("/issuers", headers=HEADERS)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert r.json() == []


def test_list_issuers_returns_distinct_names(client):
    _make_instrument(client, "Alpha Capital LP")
    _make_instrument(client, "Beta Robotics Inc.")
    _make_instrument(client, "Alpha Capital LP")  # duplicate

    r = client.get("/issuers", headers=HEADERS)
    assert r.status_code == 200
    names = r.json()
    assert "Alpha Capital LP" in names
    assert "Beta Robotics Inc." in names
    # Duplicates collapsed
    assert names.count("Alpha Capital LP") == 1
    # Sorted
    assert names == sorted(names)


def test_list_issuers_requires_auth():
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as fresh:
        r = fresh.get("/issuers")
        assert r.status_code in (401, 503)
