"""Phase 2.6b -- compliance rule CRUD API.

Versioned write: creating a new version supersedes the previous
one by setting its effective_to. The API never deletes rows.
"""

from datetime import date, timedelta

HEADERS = {"X-API-Key": "test-key-123"}


def _create(client, **overrides):
    payload = {
        "package_name": "traditional",
        "rule_name": "api_test_rule",
        "label": "API test rule",
        "applies_to": [],
        "finding_code": "API_TEST",
        "severity": "info",
        "message": "test",
        "condition": {"==": [1, 1]},
        "effective_from": date.today().isoformat(),
        "created_by": "api-test",
    }
    payload.update(overrides)
    return client.post("/compliance/rules", json=payload, headers=HEADERS)


def test_create_first_version(client):
    r = _create(client)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["version"] == 1
    assert body["effective_to"] is None
    assert body["active"] is True


def test_create_second_version_supersedes(client):
    _create(client)
    r = _create(
        client,
        effective_from=(date.today() + timedelta(days=30)).isoformat(),
    )
    assert r.status_code == 201, r.text
    assert r.json()["version"] == 2

    hist = client.get(
        "/compliance/rules/traditional/api_test_rule",
        headers=HEADERS,
    )
    assert hist.status_code == 200
    rows = hist.json()
    assert len(rows) == 2
    v1 = next(x for x in rows if x["version"] == 1)
    v2 = next(x for x in rows if x["version"] == 2)
    assert v1["effective_to"] == (
        date.today() + timedelta(days=29)
    ).isoformat()
    assert v2["effective_to"] is None


def test_second_version_must_be_later(client):
    _create(client)
    r = _create(client)  # same effective_from
    assert r.status_code == 409


def test_list_rules_excludes_future_versions(client):
    _create(client)
    _create(
        client,
        effective_from=(date.today() + timedelta(days=30)).isoformat(),
    )
    r = client.get("/compliance/rules?package_name=traditional", headers=HEADERS)
    assert r.status_code == 200
    matches = [x for x in r.json() if x["rule_name"] == "api_test_rule"]
    assert len(matches) == 1
    assert matches[0]["version"] == 1  # v2 not yet effective


def test_deactivate_excludes_from_list(client):
    r = _create(client)
    rule_id = r.json()["id"]

    d = client.post(
        f"/compliance/rules/{rule_id}/deactivate",
        headers=HEADERS,
    )
    assert d.status_code == 200, d.text
    assert d.json()["active"] is False

    r2 = client.get(
        "/compliance/rules?package_name=traditional",
        headers=HEADERS,
    )
    assert not any(
        x["id"] == rule_id for x in r2.json()
    )


def test_deactivate_is_idempotent_error(client):
    r = _create(client)
    rule_id = r.json()["id"]
    client.post(f"/compliance/rules/{rule_id}/deactivate", headers=HEADERS)
    d = client.post(
        f"/compliance/rules/{rule_id}/deactivate",
        headers=HEADERS,
    )
    assert d.status_code == 409


def test_unknown_severity_rejected(client):
    r = _create(client, severity="critical")
    assert r.status_code == 422  # pydantic pattern


def test_history_404_for_unknown_rule(client):
    r = client.get(
        "/compliance/rules/traditional/nonexistent",
        headers=HEADERS,
    )
    assert r.status_code == 404
