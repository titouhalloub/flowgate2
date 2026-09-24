# A viewer must be rejected on write routes. A reviewer must be allowed.
from app.auth import AuthUser, require_user
from app.main import app


def _auth(role):
    return AuthUser(
        id=f"{role}-1",
        email=f"{role}@example.com",
        role=role,
        auth_method="clerk",
        external_auth_id=f"{role}-1",
    )


def _instrument_body(issuer):
    return {
        "transaction_type": "equity",
        "compliance_mode": "traditional",
        "issuer_name": issuer,
        "issuer_type": "Corporate",
        "amount": 1000000.0,
        "currency": "USD",
    }


def test_viewer_cannot_create_instrument(client):
    app.dependency_overrides[require_user] = lambda: _auth("viewer")
    try:
        r = client.post("/instruments", json=_instrument_body("X"))
        assert r.status_code == 403, r.text
    finally:
        app.dependency_overrides.clear()


def test_reviewer_can_create_instrument(client):
    app.dependency_overrides[require_user] = lambda: _auth("reviewer")
    try:
        r = client.post("/instruments", json=_instrument_body("Y"))
        assert r.status_code == 201, r.text
    finally:
        app.dependency_overrides.clear()


def test_viewer_cannot_edit_compliance_rules(client):
    app.dependency_overrides[require_user] = lambda: _auth("viewer")
    try:
        r = client.post("/compliance/rules", json={
            "package_name": "X", "rule_name": "y", "label": "z",
            "applies_to": [], "finding_code": "x", "severity": "review",
            "message": "m", "condition": {}, "effective_from": "2026-01-01",
            "created_by": "test",
        })
        assert r.status_code == 403, r.text
    finally:
        app.dependency_overrides.clear()


def test_viewer_can_still_read_cap_table(client):
    app.dependency_overrides[require_user] = lambda: _auth("viewer")
    try:
        r = client.get("/cap-table/Nonexistent%20Issuer")
        # 200 or 404 both acceptable — the point is it's not 403.
        assert r.status_code in (200, 404), r.text
    finally:
        app.dependency_overrides.clear()