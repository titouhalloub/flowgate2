# Output Layer Plan — Reporting, Export, Webhooks, Connectors

**Status:** Design
**Owner:** Founder
**Last updated:** 2026-09-22

The four capabilities Flowgate does not yet have: reporting, push to external tools, export, and webhooks. This document is the plan for building them, in the order that unblocks pilots fastest.

---

## The core insight

Flowgate's promise is *"documents become governed operational data."* Today, that data dies inside Flowgate. It goes in (documents) and gets transformed (extraction, compliance, cap table), but it does not come out. Every pilot customer will ask the same three questions in week one:

1. *"Where does the data go?"*
2. *"Can I get it into my system?"*
3. *"Can I show my LPs what happened?"*

Answer all three and there is a sellable product. Answer none and there is a demo.

---

## Priority order — by customer value, not engineering interest

| Phase | Deliverable | Effort | Unblocks |
|---|---|---|---|
| **P1** | CSV export endpoint + UI button | 3 hours | Any pilot |
| **P1** | API documentation page | 4 hours | Technical buyers |
| **P2** | Webhook on document-processed | 4 hours | Automation-focused pilots |
| **P3** | Basic LP report (PDF/HTML) | 2 days | Fund-admin + family-office buyers |
| **P3** | Compliance audit report | 1 day | Regulated buyers, Islamic funds |
| **P4** | Carta connector | 4–8 weeks | Only if a signed customer demands it |
| **P4** | Allvue / DealCloud connectors | 4–8 weeks each | Only if a signed customer demands it |

Do not skip to P4 without a signed design partner asking for it by name. Connectors are six-month projects that pay off only when a customer is actively using them.

---

## Phase 1 — Export and API (one week of work, do it now)

### 1.1 — CSV export endpoint

**Route:** `GET /export/documents.csv?issuer_name=&from=&to=`

Returns every processed document for the given issuer as CSV. One row per document. Columns:

```
document_id, filename, document_type, classification_confidence,
extraction_confidence, issuer_name, counterparty, amount, currency,
status, created_at, compliance_outcome, schema_name
```

**Route:** `GET /export/cap-table/{issuer}.csv`

Returns the replay of the cap table at the current date. One row per holder. Columns:

```
holder_name, security_name, security_type, shares, ownership_percent,
vested_shares, unvested_shares, price_per_share, cost_basis
```

**Route:** `GET /export/ledger.csv?issuer_name=&entry_type=`

Returns every ledger entry. Columns:

```
entry_id, timestamp, entry_type, instrument_id, document_id,
actor, event, outcome, trace_id
```

**Effort:** 3 hours backend, 1 hour frontend button.

**Why it matters:** This is the smallest possible "data goes out" story. Every pilot can use it. It costs nothing to maintain.

### 1.2 — API documentation

Not a full OpenAPI generation exercise. One static page in the app at `/docs` (or a markdown file served by the FastAPI app) listing:

- Authentication (the API key header)
- Every GET endpoint with a one-line description
- Every POST endpoint with a body schema and one example
- Error codes (400, 404, 409) and what each means

**Effort:** 4 hours.

**Why it matters:** A technical buyer evaluating Flowgate for a pilot will read the API doc before they read the pitch deck. It is the second document they touch after the website.

### 1.3 — Example: "get all documents for one issuer in Python"

One code snippet, in the API doc:

```python
import httpx
r = httpx.get(
    "https://flowgate2.onrender.com/export/documents.csv",
    headers={"X-API-Key": "..."},
    params={"issuer_name": "Acme Robotics, Inc."},
)
open("acme_documents.csv", "wb").write(r.content)
```

That is the seed of a case study.

---

## Phase 2 — Webhook (one afternoon, do it after P1)

### 2.1 — Webhook registration

**Route:** `POST /webhooks` with body `{url, events: [...], secret}`

Stores a per-API-key webhook subscription. Only the events the customer wants.

Events to emit:

- `document.processed` — payload: document_id, issuer, type, confidence, status
- `document.routed_to_review` — same shape, status=review_needed
- `proposal.approved` — proposal_id, event_id, issuer
- `capital_call.approved` — call_id, funder, amount, currency
- `cap_table_event.recorded` — event_id, security, holder, quantity

### 2.2 — Delivery

For each event, POST the JSON payload to the registered URL with an HMAC signature header:

```
X-Flowgate-Signature: sha256=<hmac>
X-Flowgate-Event: document.processed
```

Retry on 5xx with exponential backoff (3 attempts). Log every delivery in the ledger so `GET /webhooks/{id}/deliveries` shows recent attempts.

**Effort:** 4 hours backend.

**Why it matters:** Turns Flowgate from "a thing you log into" into "a thing that feeds your existing stack." Any pilot with an ops engineer will ask for this.

---

## Phase 3 — Reports (one week, when a pilot asks)

### 3.1 — LP quarterly report (PDF or HTML)

**Route:** `GET /reports/lp-quarterly/{issuer}?quarter=2026-Q3`

Generates a templated report with:

- Fund name, quarter, reporting date
- Cap table summary (positions, ownership %)
- Capital calls during the quarter (called, received, outstanding)
- Compliance summary (documents processed, flagged, resolved)
- Proposed and approved events during the quarter

**Format:** HTML first, with a print stylesheet. Do not build PDF generation yet — HTML renders to PDF in every browser.

**Effort:** 2 days (mostly template design).

### 3.2 — Compliance audit report

**Route:** `GET /reports/compliance/{issuer}?from=&to=`

For regulated buyers and Islamic funds:

- Every rule evaluated in the period
- Every finding (blocking, review, info) with timestamps
- Every human review decision with reviewer name
- Every version of every applicable rule

This is what a Shariah auditor or an FCA examiner would want to see. It is the report that justifies the dual-mode compliance positioning.

**Effort:** 1 day.

---

## Phase 4 — Connectors (only with a signed customer)

Each connector is its own 4–8 week project. Do not start any of them until a design partner says "we need to push into Carta specifically" and puts it in the pilot contract.

When that happens, the shape is:

```
POST /integrations/carta
POST /integrations/allvue
POST /integrations/dealcloud
```

Each takes the same internal payload (an event or a document) and pushes it to the target system. The mapping layer is where the work is — Carta's security model, Allvue's fund hierarchy, DealCloud's relationship graph are all different.

Rough effort per connector:

- Mapping design: 1 week
- Auth + sandbox setup: 1 week
- Delivery + retry + logging: 1 week
- Testing against customer's real account: 1 week
- Buffer: 1–4 weeks

**Do not build these speculatively.** The value of a connector is zero without a customer on the other end.

---

## What the pitch says (adjust the use-of-funds slide)

```
Product + Integrations — core workflow engine, API surface,
CSV export, webhook event delivery, and design-partner-driven
connectors as demand requires.
```

Not "connectors to Carta, Allvue, DealCloud" as if they are already built. Say what is actually true and what is next.

---

## What this plan actually closes

**The pilot story becomes:**

> *"Send us one document type. We will extract it, apply your compliance rules, log every decision, and push the structured output to your system via CSV or webhook. You can pull it into your existing stack the same day."*

That is a real pilot. It is small enough to start next week. And it does not require a single connector to have been built.

**The honest timeline:**

- Week 1: P1 (CSV export + docs)
- Week 2: P2 (webhooks)
- Weeks 3–4: P3 (reports) — after a pilot asks
- Months 3+: P4 (connectors) — after a signed customer commits

Total to a sellable pilot offering: **one week of work.** The rest of the plan activates as customers ask, not before.

---

## One thing to be clear about in the pitch

The current pitch lists "downstream connectors to Carta, Allvue, DealCloud" in the use-of-funds slide. That is a future claim. It is fine to say *"connectors funded by this round, driven by design-partner needs"* — that is a plan. It is not fine to say *"connectors to Carta"* as if they exist. Investors ask. Have the honest answer.

Same with reporting: *"Reports are built when a design partner needs them; the underlying data model supports it today."* That is true and defensible.

The build plan above is what makes those statements true over the next six months.