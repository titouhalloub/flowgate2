"""End-to-end smoke test for the Flowgate API.

AI-ASSISTANT-AND-COMPLIANCE-PLAN.md, Part 5 step 2: exercises every critical
endpoint against a live backend and prints [PASS]/[FAIL] per check. Exits 0
only when every check passes.

Usage:
    python smoke_test.py --base-url http://127.0.0.1:8000 --api-key <key>

Env fallbacks: SMOKE_BASE_URL, SMOKE_API_KEY.
The server MUST have A27_API_KEYS configured -- auth is fail-closed (an empty
allowlist answers 503, never 200), so a green run also proves auth is set up.

One check, ``assistant-knows-a-convertible``, additionally REQUIRES a live LLM
key on the server (A27_OPENROUTER_API_KEY or A27_ANTHROPIC_API_KEY). It is
expected to FAIL against a keyless backend, by design -- see the comment on
that check.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

FAILURES: list[str] = []

# Verbatim from tests/test_safe.py -- gate-proven: heuristic classification
# >= 0.75 and extraction confidence 1.0 (not routed to review). No LLM keys
# needed; the pipeline runs on the heuristic backend.
SAFE_TEXT = """SIMPLE AGREEMENT FOR FUTURE EQUITY
Y Combinator Post-Money SAFE

Acme Robotics, Inc. (the "Company")

The Investor: Sierra Capital Partners LLC

Purchase Amount: $100,000
Post-Money Valuation Cap: $8,000,000
Discount Rate: 15%
Pro-Rata Rights: The Investor shall have pro-rata rights
MFN: This SAFE includes a Most Favored Nation clause

This SAFE is convertible upon the closing of a Priced Equity Round
(liquidity capitalization) or a dissolution event.
"""


def check(label: str, ok: bool, detail: str) -> None:
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {label:<22} {detail}", flush=True)
    if not ok:
        FAILURES.append(label)


def main() -> int:
    parser = argparse.ArgumentParser(description="Flowgate end-to-end smoke test.")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument(
        "--api-key", default=os.environ.get("SMOKE_API_KEY", "")
    )
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    client = httpx.Client(
        base_url=base, headers={"X-API-Key": args.api_key}, timeout=30.0
    )
    now = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    issuer = f"SmokeTest Issuer {now}"

    # 1. Server up (no auth required by design: it is the Render healthcheck).
    try:
        r = client.get("/health")
        check("server-up", r.status_code == 200, f"GET /health -> {r.status_code}")
    except httpx.RequestError as exc:
        check("server-up", False, f"GET /health -> transport error: {exc}")
        return 1

    # 2. A list endpoint returns 200 without needing any real resource.
    r = client.get("/cap-table-proposals")
    check(
        "list-no-resource",
        r.status_code == 200,
        f"GET /cap-table-proposals (with key) -> {r.status_code}",
    )

    # 3. Auth accepted, resource genuinely missing -> 404 IS the proof.
    r = client.get("/valuations/SmokeTest%20Nonexistent/latest")
    check(
        "auth-accepted",
        r.status_code == 404,
        f"GET /valuations/SmokeTest%20Nonexistent/latest (with key) -> {r.status_code}",
    )

    # 4. Investor (the cap-table holder).
    r = client.post(
        "/investors",
        json={"name": f"Smoke Holder {now}", "investor_type": "individual"},
    )
    check("create-investor", r.status_code == 201, f"POST /investors -> {r.status_code}")
    holder_id = r.json().get("id") if r.status_code == 201 else None

    # 5. Instrument container (its issuer gets backfilled by the SAFE below).
    r = client.post(
        "/instruments",
        json={
            "transaction_type": "equity",
            "compliance_mode": "traditional",
            "issuer_name": issuer,
            "issuer_type": "Corporate",
            "amount": 1000000.0,
            "currency": "USD",
        },
    )
    check(
        "create-instrument", r.status_code == 201, f"POST /instruments -> {r.status_code}"
    )
    instrument_id = r.json().get("id") if r.status_code == 201 else None

    # 6. Security for the issuance event.
    r = client.post(
        "/securities",
        json={
            "issuer_name": issuer,
            "name": "Common Stock",
            "security_type": "common",
            "authorized_shares": 10000000.0,
            "par_value": 0.0001,
        },
    )
    check("create-security", r.status_code == 201, f"POST /securities -> {r.status_code}")
    security_id = r.json().get("id") if r.status_code == 201 else None

    # 7. Issuance event (positions are replayed, never stored).
    if security_id and holder_id:
        r = client.post(
            "/cap-table-events",
            json={
                "security_id": security_id,
                "event_type": "issuance",
                "holder_id": holder_id,
                "quantity": 1000000,
                "price_per_share": 1.0,
                "effective_date": datetime.now(timezone.utc).isoformat(),
            },
        )
        check(
            "record-issuance",
            r.status_code == 201,
            f"POST /cap-table-events -> {r.status_code}",
        )

    # 8. Cap table snapshot replays the event.
    r = client.get(f"/cap-table/{quote(issuer)}")
    positions = r.json().get("positions", []) if r.status_code == 200 else []
    check(
        "cap-table-read",
        r.status_code == 200 and len(positions) >= 1,
        f"GET /cap-table/{{issuer}} -> {r.status_code}, positions={len(positions)}",
    )

    # 9./10. 409A FMV: record, then read back with the staleness nag.
    r = client.post(
        "/valuations",
        json={
            "issuer_name": issuer,
            "valuation_date": datetime.now(timezone.utc).isoformat(),
            "price_per_share": 2.0,
            "valuation_type": "fmv_409a",
            "method": "smoke",
        },
    )
    check("record-409a", r.status_code == 201, f"POST /valuations -> {r.status_code}")

    r = client.get(f"/valuations/{quote(issuer)}/latest")
    latest = r.json() if r.status_code == 200 else {}
    check(
        "read-409a",
        r.status_code == 200 and isinstance(latest.get("is_stale"), bool),
        f"GET /valuations/{{issuer}}/latest -> {r.status_code}, is_stale={latest.get('is_stale')}",
    )

    # 11. SAFE document through the full pipeline (classify -> extract ->
    # compliance gate -> ledger; the CREATE_CONVERTIBLE proposal is created
    # server-side as a side effect).
    r = client.post(
        f"/instruments/{instrument_id}/documents",
        json={"text": SAFE_TEXT, "filename": "yc_safe.pdf"},
    )
    body = r.json() if r.status_code == 200 else {}
    document = body.get("document", {})
    ok = (
        r.status_code == 200
        and document.get("status") == "processed"
        and document.get("document_type") == "safe"
    )
    check(
        "safe-pipeline",
        ok,
        f"POST /instruments/{{id}}/documents -> {r.status_code}, "
        f"type={document.get('document_type')}, status={document.get('status')}",
    )
    doc_id = document.get("id")

    # 12. The document-derived issuer is carried on the instrument (the
    # frontend auto-switches to it; the smoke test follows the same rule).
    r = client.get(f"/instruments/{instrument_id}")
    live_issuer = r.json().get("issuer_name") if r.status_code == 200 else None
    check(
        "issuer-backfilled",
        bool(live_issuer) and str(live_issuer).startswith("Acme Robotics"),
        f"GET /instruments/{{id}} -> {r.status_code}, issuer={live_issuer!r}",
    )

    # 13. The SAFE's CREATE_CONVERTIBLE proposal exists, keyed by document_id.
    r = client.get("/cap-table-proposals", params={"status": "proposed"})
    props = r.json() if r.status_code == 200 else []
    prop = next((p for p in props if p.get("document_id") == doc_id), None)
    check(
        "safe-proposal-created",
        prop is not None,
        f"GET /cap-table-proposals?status=proposed -> {r.status_code}, "
        f"matched={prop is not None}",
    )

    # 14. Human approval converts the proposal into an outstanding SAFE row.
    if prop is not None:
        r = client.post(
            f"/cap-table-proposals/{prop['id']}/approve",
            params={"reviewer": "Smoke Test Reviewer"},
        )
        approved = r.json() if r.status_code == 200 else {}
        check(
            "approve-convertible",
            r.status_code == 200 and approved.get("status") == "outstanding",
            f"POST /cap-table-proposals/{{id}}/approve?reviewer=... -> {r.status_code}, "
            f"status={approved.get('status')}",
        )
    else:
        check("approve-convertible", False, "skipped: no proposal matched the document")

    # 15. Priced-round preview computes conversions without persisting.
    r = client.post(
        "/priced-rounds/preview",
        json={
            "issuer_name": live_issuer or issuer,
            "round_price": 2.0,
            "pre_safe_shares": 1000000,
            "options_pool": 100000,
        },
    )
    preview = r.json() if r.status_code == 200 else {}
    conversions = preview.get("conversions", [])
    check(
        "preview-round",
        r.status_code == 200 and len(conversions) >= 1 and preview.get("total_new_shares", 0) > 0,
        f"POST /priced-rounds/preview -> {r.status_code}, conversions={len(conversions)}, "
        f"total_new_shares={preview.get('total_new_shares')}",
    )

    # 16. The read-only assistant answers from a populated knowledge base.
    # THIS CHECK REQUIRES A LIVE LLM KEY on the backend (A27_OPENROUTER_API_KEY
    # or A27_ANTHROPIC_API_KEY). It is the only check in this file that cannot
    # pass without one: the heuristic backend classifies documents but cannot
    # answer prose questions, so a keyless server returns "I couldn't reach the
    # language model". That failure is deliberate -- a demo-visible red line
    # beats a silently mute assistant that looks healthy.
    # It doubles as a deploy check: an image built without the repo-root
    # markdown answers "knowledge base is empty" (Dockerfile COPY *.md ./).
    # The per-request timeout exceeds the server's own 55s LLM timeout so a
    # slow model reports as a FAIL rather than a transport error.
    try:
        r = client.post(
            "/assistant/ask",
            json={"question": "What is a convertible?"},
            timeout=90.0,
        )
        answer = r.json().get("answer", "") if r.status_code == 200 else ""
        check(
            "assistant-knows-a-convertible",
            (
                r.status_code == 200
                and bool(answer.strip())
                and "knowledge base is empty" not in answer
                and "couldn't reach the language model" not in answer
            ),
            f"POST /assistant/ask -> {r.status_code}, answer={answer[:60]!r}",
        )
    except httpx.RequestError as exc:
        check(
            "assistant-knows-a-convertible",
            False,
            f"POST /assistant/ask -> transport error: {exc}",
        )

    print()
    if FAILURES:
        print(f"SMOKE TEST: {len(FAILURES)} failure(s): {', '.join(FAILURES)}")
        return 1
    print("SMOKE TEST: all checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

