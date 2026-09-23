"""Tests for the CSV/XLSX export endpoints."""

from __future__ import annotations

HEADERS = {"X-API-Key": "test-key-123"}


def test_documents_csv_has_header(client):
    r = client.get("/export/documents.csv", headers=HEADERS)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers.get("content-disposition", "")
    body = r.content.decode("utf-8-sig")
    first = body.splitlines()[0]
    assert first.startswith("document_id,")
    assert "classification_confidence" in first


def test_documents_xlsx_has_signature(client):
    r = client.get("/export/documents.xlsx", headers=HEADERS)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument"
    )
    assert r.content[:2] == b"PK"


def test_ledger_csv_has_header(client):
    r = client.get("/export/ledger.csv", headers=HEADERS)
    assert r.status_code == 200, r.text
    body = r.content.decode("utf-8-sig")
    first = body.splitlines()[0]
    assert first.startswith("entry_id,")
    assert "entry_type" in first


def test_ledger_xlsx_has_signature(client):
    r = client.get("/export/ledger.xlsx", headers=HEADERS)
    assert r.status_code == 200, r.text
    assert r.content[:2] == b"PK"


def test_export_requires_auth():
    """Requests without an X-API-Key must be rejected.

    The default `client` fixture sends the header automatically, so this
    test builds a fresh TestClient with no defaults. An empty allowlist
    answers 503; a populated allowlist without a key answers 401.
    """
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as fresh:
        for path in ("/export/documents.csv", "/export/ledger.csv"):
            r = fresh.get(path)
            assert r.status_code in (401, 503), f"{path} -> {r.status_code}"
