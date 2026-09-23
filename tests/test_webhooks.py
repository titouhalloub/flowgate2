# Tests for the webhook layer.
from __future__ import annotations

import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import pytest

HEADERS = {"X-API-Key": "test-key-123"}


class _MockReceiver(BaseHTTPRequestHandler):
    received = []

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        type(self).received.append({
            "signature": self.headers.get("X-Flowgate-Signature"),
            "event": self.headers.get("X-Flowgate-Event"),
            "delivery": self.headers.get("X-Flowgate-Delivery"),
            "timestamp": self.headers.get("X-Flowgate-Timestamp"),
            "body": body,
        })
        self.send_response(200)
        self.end_headers()

    def log_message(self, *a, **k):
        pass


@pytest.fixture
def receiver():
    _MockReceiver.received = []
    srv = HTTPServer(("127.0.0.1", 0), _MockReceiver)
    t = Thread(target=srv.serve_forever, daemon=True)
    t.start()
    host, port = srv.server_address
    yield f"http://{host}:{port}/hook"
    srv.shutdown()


def _make_sub(client, url, events=None):
    r = client.post(
        "/webhooks",
        headers=HEADERS,
        json={
            "url": url,
            "secret": "test-secret-please-change-16chars",
            "events": events or [],
            "created_by": "test",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_create_and_list_subscription(client, receiver):
    sub = _make_sub(client, receiver, ["document.processed"])
    assert sub["url"] == receiver
    assert sub["active"] is True

    r = client.get("/webhooks", headers=HEADERS)
    assert r.status_code == 200
    ids = [s["id"] for s in r.json()]
    assert sub["id"] in ids


def test_test_endpoint_delivers(client, receiver):
    sub = _make_sub(client, receiver)
    r = client.post(f"/webhooks/{sub['id']}/test", headers=HEADERS)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "success", out
    assert out["response_status"] == 200
    assert len(_MockReceiver.received) == 1
    assert _MockReceiver.received[0]["event"] == "webhook.test"
    assert _MockReceiver.received[0]["signature"].startswith("sha256=")


def test_delete_deactivates(client, receiver):
    sub = _make_sub(client, receiver)
    r = client.delete(f"/webhooks/{sub['id']}", headers=HEADERS)
    assert r.status_code == 204
    r = client.get("/webhooks", headers=HEADERS)
    by_id = {s["id"]: s for s in r.json()}
    assert by_id[sub["id"]]["active"] is False


def test_deliveries_list(client, receiver):
    sub = _make_sub(client, receiver)
    client.post(f"/webhooks/{sub['id']}/test", headers=HEADERS)
    r = client.get(f"/webhooks/{sub['id']}/deliveries", headers=HEADERS)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 1
    assert rows[0]["event_type"] == "webhook.test"
    assert rows[0]["status"] == "success"


def test_failed_delivery_records_error(client):
    sub = _make_sub(client, "http://127.0.0.1:1/dead")
    r = client.post(f"/webhooks/{sub['id']}/test", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["status"] == "failed"
    assert r.json()["last_error"]


def test_retry_endpoint(client, receiver):
    sub = _make_sub(client, receiver)
    r = client.post(f"/webhooks/{sub['id']}/test", headers=HEADERS)
    delivery_id = r.json()["delivery_id"]

    r = client.post(f"/webhooks/deliveries/{delivery_id}/retry", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["status"] == "success"
    assert len(_MockReceiver.received) == 2


def test_hmac_signature_is_verifiable(client, receiver):
    sub = _make_sub(client, receiver)
    client.post(f"/webhooks/{sub['id']}/test", headers=HEADERS)

    received = _MockReceiver.received[-1]
    assert received["signature"].startswith("sha256=")
    sig_hex = received["signature"].split("=", 1)[1]
    assert len(sig_hex) == 64

    ts = received["timestamp"]
    body = received["body"]
    expected = hmac.new(
        b"test-secret-please-change-16chars",
        f"{ts}.".encode() + body,
        hashlib.sha256,
    ).hexdigest()
    assert expected == sig_hex
