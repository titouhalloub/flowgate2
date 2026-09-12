"""Phase D -- transfer rules / ROFR governance gate.

Rules are prepared governance; a named human disposes. These tests drive
the full loop over HTTP: create a rule, propose a TRANSFER, hit the gate,
resolve the queue, and verify what did (and did not) reach the append-only
cap-table log. See PHASE-D-TRANSFER-RULES.md.
"""
from fastapi.testclient import TestClient

HEADERS = {"X-API-Key": "test-key-123"}
REVIEWER = "M. Vance"


def _make_instrument(client: TestClient, issuer_name: str = "Demo Acme Inc"):
    return client.post(
        "/instruments",
        headers=HEADERS,
        json={
            "transaction_type": "private_equity",
            "compliance_mode": "traditional",
            "issuer_name": issuer_name,
            "issuer_type": "Corporate",
            "amount": 10_000_000,
            "currency": "USD",
        },
    )


def _make_investor(client: TestClient, name: str):
    return client.post(
        "/investors",
        headers=HEADERS,
        json={"name": name, "investor_type": "institution"},
    )


def _make_security(
    client: TestClient,
    issuer_name: str = "Demo Acme Inc",
    name: str = "Common Stock",
    authorized_shares: float = 10_000_000,
):
    return client.post(
        "/securities",
        headers=HEADERS,
        json={
            "issuer_name": issuer_name,
            "name": name,
            "security_type": "common",
            "authorized_shares": authorized_shares,
        },
    )


def _issue(client: TestClient, security_id: str, holder_id: str, quantity: float):
    """Seed a holder with shares (no rules fire on issuances)."""
    return client.post(
        "/cap-table-events",
        headers=HEADERS,
        json={
            "security_id": security_id,
            "event_type": "issuance",
            "holder_id": holder_id,
            "quantity": quantity,
            "effective_date": "2026-01-01T00:00:00",
        },
    )


def _transfer(
    client: TestClient,
    security_id: str,
    from_holder_id: str,
    holder_id: str,
    quantity: float,
):
    return client.post(
        "/cap-table-events",
        headers=HEADERS,
        json={
            "security_id": security_id,
            "event_type": "transfer",
            "holder_id": holder_id,
            "from_holder_id": from_holder_id,
            "quantity": quantity,
            "effective_date": "2026-06-01T00:00:00",
        },
    )


def _create_rule(client: TestClient, issuer_name: str, **overrides):
    payload = {
        "issuer_name": issuer_name,
        "rule_type": "rofr",
        "condition": {"exempt_holder_ids": []},
        "gate": "review",
        "approver": "General Counsel",
        "created_by": "M. Vance",
    }
    payload.update(overrides)
    return client.post("/transfer-rules", headers=HEADERS, json=payload)


def _setup_company(client: TestClient):
    """One issuer, one security, two funded holders. Returns ids."""
    _make_instrument(client)
    security_id = _make_security(client).json()["id"]
    seller = _make_investor(client, "Seller LP").json()["id"]
    buyer = _make_investor(client, "Buyer LP").json()["id"]
    r = _issue(client, security_id, seller, 1_000_000)
    assert r.status_code == 201, r.text
    return {"security_id": security_id, "seller": seller, "buyer": buyer}


# --------------------------------------------------------------------------- #
# Rule management + validation
# --------------------------------------------------------------------------- #


def test_create_and_list_rules(client: TestClient):
    r = _create_rule(client, "Demo Acme Inc")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["rule_type"] == "rofr"
    assert body["gate"] == "review"
    assert body["active"] is True

    listed = client.get(
        "/transfer-rules", headers=HEADERS, params={"issuer_name": "Demo Acme Inc"}
    )
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [body["id"]]


def test_unknown_rule_type_rejected_400(client: TestClient):
    r = _create_rule(client, "Demo Acme Inc", rule_type="vibes")
    assert r.status_code == 400


def test_malformed_condition_rejected_400(client: TestClient):
    # exempt_holder_ids must be a list -- a string would break the engine
    # at evaluation time; garbage is stopped at the door instead.
    r = _create_rule(
        client,
        "Demo Acme Inc",
        condition={"exempt_holder_ids": "seller-id"},
    )
    assert r.status_code == 400

    r = _create_rule(
        client,
        "Demo Acme Inc",
        rule_type="bylaw_lockup",
        condition={"holder_ids": ["x"], "until_date": "2027-01-01"},
        gate="block",
        window_days=-5,
    )
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Review gate: ROFR routes a transfer to the queue
# --------------------------------------------------------------------------- #


def test_rofr_review_gate_pending_then_approve_writes_transfer(client: TestClient):
    ids = _setup_company(client)
    _create_rule(client, "Demo Acme Inc")  # ROFR review on every transfer

    proposed = _transfer(client, ids["security_id"], ids["seller"], ids["buyer"], 400_000)
    assert proposed.status_code == 409, proposed.text
    evaluation_id = proposed.json()["detail"]["transfer_evaluation_id"]
    assert evaluation_id

    queued = client.get(
        "/transfer-evaluations", headers=HEADERS, params={"outcome": "pending"}
    )
    assert queued.status_code == 200
    rows = queued.json()
    assert any(row["id"] == evaluation_id for row in rows)
    assert rows[0]["outcome"] == "pending"

    # Named human approves -> the transfer event is written.
    ok = client.post(
        f"/transfer-evaluations/{evaluation_id}/approve",
        headers=HEADERS,
        params={"reviewer": REVIEWER},
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["outcome"] == "approved"
    assert body["reviewer"] == REVIEWER
    assert body["reviewed_at"]

    # Approving twice is refused.
    again = client.post(
        f"/transfer-evaluations/{evaluation_id}/approve",
        headers=HEADERS,
        params={"reviewer": REVIEWER},
    )
    assert again.status_code == 409


def test_rofr_exempt_holder_transfers_freely(client: TestClient):
    ids = _setup_company(client)
    _create_rule(
        client,
        "Demo Acme Inc",
        condition={"exempt_holder_ids": [ids["seller"]]},
    )
    r = _transfer(client, ids["security_id"], ids["seller"], ids["buyer"], 250_000)
    assert r.status_code == 201, r.text
    queued = client.get(
        "/transfer-evaluations", headers=HEADERS, params={"outcome": "pending"}
    )
    assert queued.json() == []


def test_reject_writes_nothing(client: TestClient):
    ids = _setup_company(client)
    _create_rule(client, "Demo Acme Inc")

    proposed = _transfer(client, ids["security_id"], ids["seller"], ids["buyer"], 400_000)
    evaluation_id = proposed.json()["detail"]["transfer_evaluation_id"]

    ok = client.post(
        f"/transfer-evaluations/{evaluation_id}/reject",
        headers=HEADERS,
        params={"reviewer": REVIEWER},
    )
    assert ok.status_code == 200
    assert ok.json()["outcome"] == "rejected"

    # The transfer never landed: the seller still holds all 1,000,000 shares.
    # Proof: exempting the seller lets the full block move with no overdraft.
    _create_rule(
        client,
        "Demo Acme Inc",
        condition={"exempt_holder_ids": [ids["seller"]]},
    )
    fresh = _transfer(client, ids["security_id"], ids["seller"], ids["buyer"], 1_000_000)
    assert fresh.status_code == 201, fresh.text

    # A resolved evaluation cannot be resolved again.
    again = client.post(
        f"/transfer-evaluations/{evaluation_id}/reject",
        headers=HEADERS,
        params={"reviewer": REVIEWER},
    )
    assert again.status_code == 409


# --------------------------------------------------------------------------- #
# BLOCK gate + quantity thresholds
# --------------------------------------------------------------------------- #


def test_block_gate_blocks_transfer_and_cap_table_unchanged(client: TestClient):
    ids = _setup_company(client)
    _create_rule(
        client,
        "Demo Acme Inc",
        rule_type="bylaw_lockup",
        condition={
            "holder_ids": [ids["seller"]],
            "until_date": "2027-01-01",
        },
        gate="block",
    )
    r = _transfer(client, ids["security_id"], ids["seller"], ids["buyer"], 100_000)
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["message"] == "Transfer blocked by governance rule"
    assert detail["blocking_rule_id"]

    queued = client.get(
        "/transfer-evaluations", headers=HEADERS, params={"outcome": "blocked"}
    )
    assert queued.status_code == 200
    assert len(queued.json()) == 1

    # A resolve attempt on a non-pending evaluation is refused.
    ev_id = queued.json()[0]["id"]
    ok = client.post(
        f"/transfer-evaluations/{ev_id}/approve",
        headers=HEADERS,
        params={"reviewer": REVIEWER},
    )
    assert ok.status_code == 409


def test_board_approval_threshold_small_transfer_allowed_large_pending(
    client: TestClient,
):
    ids = _setup_company(client)
    _create_rule(
        client,
        "Demo Acme Inc",
        rule_type="board_approval",
        condition={"min_quantity": 500_000},
    )
    small = _transfer(client, ids["security_id"], ids["seller"], ids["buyer"], 499_999)
    assert small.status_code == 201, small.text

    large = _transfer(client, ids["security_id"], ids["seller"], ids["buyer"], 600_000)
    assert large.status_code == 409
    assert large.json()["detail"]["message"] == "Transfer requires governance approval"


def test_non_transfer_events_bypass_the_gate(client: TestClient):
    ids = _setup_company(client)
    _create_rule(client, "Demo Acme Inc")  # would catch every transfer
    r = _issue(client, ids["security_id"], ids["buyer"], 10)
    assert r.status_code == 201, r.text
    queued = client.get(
        "/transfer-evaluations", headers=HEADERS, params={"outcome": "pending"}
    )
    assert queued.json() == []
