# Flowgate API

The Flowgate backend is a FastAPI application exposing the governed
execution pipeline: document intake, extraction, compliance evaluation,
cap-table proposals, capital-call orchestration, and the unified audit
ledger.

## Base URL

    Production:  https://flowgate2.onrender.com
    Local:       http://localhost:8000

## Authentication

Two paths, one requirement. Every authenticated route accepts either.

### 1. API key (programmatic)

Send the key in an X-API-Key header. Keys are configured on the server
via the A27_API_KEYS environment variable (comma-separated allowlist).
The API key path maps to a synthetic admin identity.

    curl -H "X-API-Key: $FLOWGATE_API_KEY" \
         https://flowgate2.onrender.com/investors

### 2. Clerk JWT (UI)

The web app authenticates users via Clerk. Every request from the
browser carries an RS256-signed JWT in the Authorization header. Tokens
are verified server-side against Clerk's JWKS endpoint - no secret key
lives on the backend.

    Authorization: Bearer <jwt>

The JWT's sub claim is looked up in the users table; the associated
role determines what the user can do.

### Fail-closed

If the API key allowlist is empty AND no valid JWT is provided, every
authenticated route answers 503. This is deliberate - a misconfigured
server never silently accepts unauthenticated traffic.

## Roles

| Role | Can do | Cannot do |
|---|---|---|
| admin | Everything | - |
| compliance_officer | Edit rules, review findings | Manage users |
| reviewer | Approve proposals and capital calls | Edit rules |
| viewer | Read everything | Any write |

The API key path always has admin. New Clerk users default to viewer;
promote them by updating the role column in the users table.

## Quickstart (curl)

Create an investor:

    curl -X POST https://flowgate2.onrender.com/investors \
      -H "X-API-Key: $FLOWGATE_API_KEY" \
      -H "Content-Type: application/json" \
      -d '{"name": "Acme Capital LP", "investor_type": "fund"}'

Create an instrument (the deal container):

    curl -X POST https://flowgate2.onrender.com/instruments \
      -H "X-API-Key: $FLOWGATE_API_KEY" \
      -H "Content-Type: application/json" \
      -d '{"transaction_type": "equity", "compliance_mode": "traditional", "issuer_name": "Acme Robotics, Inc.", "issuer_type": "Corporate", "amount": 5000000, "currency": "USD"}'

Upload a document (runs classification, extraction, compliance):

    curl -X POST https://flowgate2.onrender.com/instruments/$ID/documents/upload \
      -H "X-API-Key: $FLOWGATE_API_KEY" \
      -F "file=@subscription-agreement.pdf"

Read the cap table:

    curl -H "X-API-Key: $FLOWGATE_API_KEY" \
         https://flowgate2.onrender.com/cap-table/Acme%20Robotics,%20Inc.

## Endpoints

### Health

| Method | Path | Purpose |
|---|---|---|
| GET | /health | Liveness check (unauthenticated) |
| GET | /config | Clerk publishable key for the frontend (unauthenticated) |

### Instruments

| Method | Path | Purpose |
|---|---|---|
| POST | /instruments | Create a deal container |
| GET | /instruments/{id} | Read one |
| GET | /instruments/{id}/ledger | The instrument's ledger entries |

### Documents

| Method | Path | Purpose |
|---|---|---|
| POST | /instruments/{id}/documents | Submit raw text |
| POST | /instruments/{id}/documents/upload | Upload PDF / TXT / MD / HTML / image |
| POST | /instruments/{id}/evidence | Submit review evidence |
| POST | /documents/{id}/cap-table-proposal | Turn a processed document into a proposal |

### Investors and holdings

| Method | Path | Purpose |
|---|---|---|
| POST | /investors | Create an investor |
| GET | /investors | List investors |
| POST | /instruments/{id}/holdings | Attach a holding |
| GET | /investors/{id}/portfolio | Cross-fund portfolio view |

### Cap table

| Method | Path | Purpose |
|---|---|---|
| POST | /securities | Create a security class |
| POST | /cap-table-events | Record an event (issuance, transfer, cancellation, exercise, conversion) |
| GET | /cap-table/{issuer_name} | Replay and return the snapshot |

The cap table is event-sourced. Every ownership number is computed by
replaying the append-only event log; nothing is stored as a mutable
snapshot.

### Proposals

| Method | Path | Purpose |
|---|---|---|
| GET | /cap-table-proposals | Review queue |
| POST | /cap-table-proposals/{id}/approve | Approve (requires reviewer) |
| POST | /cap-table-proposals/{id}/reject | Reject |
| POST | /cap-table-proposals/{id}/link-investor | Attach a real investor before approval |

### Capital calls

| Method | Path | Purpose |
|---|---|---|
| POST | /capital-calls | Create a call notice |
| GET | /capital-calls | List, filterable by status |
| GET | /capital-calls/overdue | Overdue queue |
| POST | /capital-calls/{id}/review | Approve or reject (named reviewer) |
| POST | /capital-calls/{id}/payments | Record a payment |
| GET | /capital-calls/{id}/payments | Payment list + derived status |

### Valuations (409A)

| Method | Path | Purpose |
|---|---|---|
| POST | /valuations | Record an FMV or preferred-price round |
| GET | /valuations/{issuer_name} | Valuation history |
| GET | /valuations/{issuer_name}/latest | Latest, with staleness flag |

### Convertibles and priced rounds

| Method | Path | Purpose |
|---|---|---|
| POST | /convertibles | Create a SAFE or convertible note |
| GET | /convertibles/{issuer_name} | List by status |
| POST | /priced-rounds/preview | Compute conversions without persisting |
| POST | /priced-rounds | Commit atomically |
| GET | /priced-rounds/{issuer_name} | List rounds |

### Compliance rules

| Method | Path | Purpose |
|---|---|---|
| GET | /compliance/rules | List, filtered by package |
| GET | /compliance/rules/{package}/{rule} | Full version history |
| POST | /compliance/rules | Create a new version |
| POST | /compliance/rules/{id}/deactivate | Deactivate a single version |

Rules are versioned by (package_name, rule_name, effective_from). A new
version closes the previous one's window the day before and increments
the version number.

### Transfer rules

| Method | Path | Purpose |
|---|---|---|
| GET | /transfer-rules | Active and inactive rules |
| POST | /transfer-rules | Create a rule |
| GET | /transfer-evaluations | Review queue |
| POST | /transfer-evaluations/{id}/approve | Approve a gated transfer |
| POST | /transfer-evaluations/{id}/reject | Reject |

### Assistant

| Method | Path | Purpose |
|---|---|---|
| POST | /assistant/ask | Read-only Q&A grounded in the plan docs |

The assistant never writes, never claims compliance, and cites its
sources. It reads from the markdown files in the repo root.

### Export

| Method | Path | Purpose |
|---|---|---|
| GET | /export/documents.csv | Every document, filterable by issuer |
| GET | /export/documents.xlsx | Same data, Excel |
| GET | /export/ledger.csv | Audit ledger, filterable by issuer or instrument |
| GET | /export/ledger.xlsx | Same data, Excel |

CSV responses carry a UTF-8 BOM so Excel auto-detects the encoding.

### Webhooks

| Method | Path | Purpose |
|---|---|---|
| POST | /webhooks | Register a subscription |
| GET | /webhooks | List |
| DELETE | /webhooks/{id} | Deactivate (soft delete) |
| GET | /webhooks/{id}/deliveries | Recent delivery attempts |
| POST | /webhooks/{id}/test | Fire a test event |
| POST | /webhooks/deliveries/{id}/retry | Retry a failed delivery |

Events fired by the pipeline: document.processed and
document.routed_to_review.

## Webhook payload

Example - a document that cleared both gates:

    {
      "event": "document.processed",
      "timestamp": "2026-09-24T03:15:22.123456+00:00",
      "data": {
        "document_id": "doc_abc123",
        "instrument_id": "inst_xyz789",
        "issuer_name": "Acme Robotics, Inc.",
        "document_type": "safe",
        "classification_confidence": 0.98,
        "extraction_confidence": 0.92,
        "status": "processed",
        "routed_to_review": false,
        "outcome": "not_applicable"
      }
    }

A document that routed to human review fires document.routed_to_review
instead.

## Verifying webhook signatures

Every delivery carries five headers:

    X-Flowgate-Signature: sha256=<hex>
    X-Flowgate-Event:     document.processed
    X-Flowgate-Delivery:  whd_<uuid>
    X-Flowgate-Timestamp: <unix_seconds>
    Content-Type:         application/json

The signature is HMAC-SHA256(secret, timestamp + "." + body).

Verify it in your receiver:

    import hashlib
    import hmac

    def verify(secret, timestamp, body, header):
        expected = hmac.new(
            secret.encode(),
            (timestamp + ".").encode() + body,
            hashlib.sha256,
        ).hexdigest()
        given = header.split("=", 1)[1] if header.startswith("sha256=") else ""
        return hmac.compare_digest(expected, given)

Reject requests whose timestamp is more than 5 minutes old to prevent
replay.

## Errors

All error responses have the shape {"detail": "<message>"}.

| Status | Meaning |
|---|---|
| 400 | Validation error (bad type, missing field, malformed condition) |
| 401 | Missing or invalid API key / JWT |
| 403 | Authenticated but insufficient role |
| 404 | Resource not found |
| 409 | Conflict (double-approve, version not strictly later, already deactivated) |
| 413 | Upload too large |
| 422 | Unparseable document - nothing was classified or extracted |
| 503 | Server has no API keys configured (fail-closed) |

## Interactive spec

The auto-generated OpenAPI spec is live at:

- /openapi.json - the raw spec
- /docs - Swagger UI with "Try it out" buttons for every route
- /redoc - read-only reference view

## Versioning

The API is pre-1.0 and changes ship continuously. The migration chain
in migrations/versions/ is the source of truth for schema history.

## Support

Contact the founder directly. There is no support portal yet.
