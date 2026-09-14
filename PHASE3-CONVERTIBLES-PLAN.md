# Phase 3 — SAFE & Convertible Conversion

This document is the source of truth for the SAFE/convertible conversion feature. It is committed here so that future contributors and AI agents can read the plan from the repo rather than from a chat thread.

## Status

- **Phase 3.1** — Models and migration ✅ complete
- **Phase 3.2** — Single-SAFE conversion math ✅ complete
- **Phase 3.3** — Multi-SAFE math and arbitration ✅ complete
- **Phase 3.4** — Preview endpoint ✅ complete
- **Phase 3.5** — Commit endpoint ✅ complete
- **Phase 3.6** — Extraction wire-up ⏳ in progress
- **Phase 3.7** — UI ⏳ not started
- **Phase 3.8** — Integration and hardening ⏳ not started

## Scope

A convertible (SAFE) is **not a share**. It is a contract for future shares. Until a trigger event fires, it lives off the cap table and does not affect ownership, fully-diluted share count, or voting. On the trigger event (a priced round), each outstanding convertible becomes an issuance of a specific number of shares at a specific computed price.

### In scope

- `Convertible` and `PricedRound` models
- `CONVERSION` cap-table event type
- Post-money SAFE conversion math with cap-vs-discount arbitration
- Preview endpoint (no persistence)
- Commit endpoint (atomic transaction)
- Ledger entries with a shared `round_id`
- Tests for the math, atomicity, and interaction boundaries

### Not in scope (Phase 3.5+ future work)

- Pre-money SAFEs (rejected with 400)
- Accrued interest on convertible notes
- MFN election mechanics
- Pro-rata rights exercise
- Partial conversion, per-investor round allocations
- Multi-currency rounds

## Pricing conventions (locked in)

**Discount price:**
```
discount_price = round_price × (1 − discount_rate)
```

**Cap price (post-money SAFE, YC 2018+ formula):**
```
owner_i = purchase_amount_i / valuation_cap_i
sum_owner = Σ owner_j
shares_i = owner_i / (1 − sum_owner) × (pre_safe_shares + options_pool)
cap_price_i = purchase_amount_i / shares_i
```

**Arbitration:** the investor receives the lower of `cap_price_i` and `discount_price`.

**Post-money SAFEs only in v1.** Pre-money SAFEs are rejected with HTTP 400.

## Interaction rules

- **409A gate:** does NOT apply to SAFE conversions. Options and warrants on common stock only. Verified by test.
- **Vesting:** conversion shares are fully vested by default. `CONVERSION` events carry no vesting fields.
- **Transfer rules:** not consulted. Conversion is a primary issuance.
- **Proposal gate:** conversion is a separate workflow with its own preview step. It does not route through the proposal queue but requires auth and a reviewer signature.
- **Idempotency:** the client sends a `client_request_id` UUID with each commit. Duplicate commits return the existing round.

## Database schema

### `convertibles`

| Column | Type | Notes |
|---|---|---|
| id | str (UUID) | Primary key |
| issuer_name | str | Indexed |
| investor_name | str | |
| document_id | str, nullable | FK to source Document |
| purchase_amount | float | |
| currency | str(3) | ISO code |
| instrument_kind | str(32) | `post_money_safe` or `pre_money_safe` |
| valuation_cap | float | |
| discount_rate | float, nullable | Fraction (0.15 = 15%) |
| pro_rata_rights | bool, nullable | Tri-state |
| mfn_clause | bool, nullable | Tri-state |
| conversion_trigger | text, nullable | |
| issued_date | date | |
| status | str(16) | `outstanding` / `converted` / `cancelled` |
| converted_at | datetime, nullable | |
| conversion_event_id | str, nullable | FK to CapTableEvent |
| created_at | datetime | |
| updated_at | datetime | |

### `priced_rounds`

| Column | Type | Notes |
|---|---|---|
| id | str (UUID) | Primary key |
| issuer_name | str | Indexed |
| round_name | str(64) | e.g. "Series A" |
| price_per_share | float | |
| round_shares | int | |
| post_money_shares | int | |
| effective_date | date | |
| reviewer | str | |
| notes | text, nullable | |
| client_request_id | str(36), unique | Idempotency key |
| created_at | datetime | |

### `cap_table_events` (additions)

- `related_convertible_id: str | None`
- `related_round_id: str | None`

## Engine conventions

- A CONVERSION event carrying `related_convertible_id` is a **pure credit** (no source security to debit). SAFEs live off the cap table.
- A CONVERSION event without `related_convertible_id` retains the existing security-to-security debit semantics.
- This discriminator is implicit. **Do not set `related_convertible_id` on security-to-security conversions.**

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/convertibles` | Create a convertible |
| GET | `/convertibles/{issuer_name}` | List (with `status` filter) |
| GET | `/convertibles/{id}` | Read one |
| POST | `/priced-rounds/preview` | Compute conversions, no persist |
| POST | `/priced-rounds` | Commit atomically |
| GET | `/priced-rounds/{issuer_name}` | List rounds |

## Phase 3.6 acceptance criteria — Extraction wire-up

**Goal:** a SAFE document uploaded through the pipeline produces a pending **proposal**; on approval, it becomes an `outstanding` `Convertible` row.

**Non-negotiable rules:**

1. **No self-certification.** The extractor must NOT write a `Convertible` row directly. It must route through the proposal gate as a new `ProposalType.CREATE_CONVERTIBLE` value. A `Convertible` row can only be created as the result of a reviewer approval.
2. **Provenance.** The `Convertible.document_id` field must be populated with the source document's id. Null is a bug.
3. **Idempotency.** If a SAFE document is re-processed, it must not create a duplicate proposal for the same `document_id`.

**Tests required:**

- Upload a SAFE document → a pending proposal of type `CREATE_CONVERTIBLE` appears
- Approve the proposal → an `outstanding` `Convertible` row exists with `document_id` set
- Reject the proposal → no `Convertible` row exists

## Phase 3.7 acceptance criteria — UI

**Goal:** a "Convertibles" panel and a "Record Priced Round" modal on the Cap Table tab.

**Convertibles panel:**

- Table showing: holder, amount, cap, discount, issued date, status
- Only shows `outstanding` convertibles by default (toggle for all)

**Record Priced Round modal — three steps:**

1. **Terms:** round name, price per share, round shares, effective date, reviewer signature
2. **Preview:** table of conversions (cap price, discount price, chosen basis, shares issued) + resulting cap table preview. Per-convertible override input.
3. **Confirm:** commit button. On success, cap table reloads and ledger entries appear.

**Post-round behavior:**

- "409A refresh recommended" badge appears on the cap table metrics strip after a commit
- Non-blocking; does not update the FMV automatically

## Risks and constraints

| Risk | Mitigation |
|---|---|
| Order-dependence with multiple SAFEs | All outstanding post-money SAFEs convert together in one commit |
| Pre-money SAFEs | Rejected with 400 in v1 |
| Multi-round SAFEs | Engine only converts `status == "outstanding"` |
| MFN clause | Captured, not enforced |
| Per-investor round allocation | Aggregate issuance in v1 |
| Currency | USD only in v1 |
| Idempotency | Client-supplied `client_request_id` with unique constraint |

## Technical debt (known, deferred)

**Boot path uses `create_all`, not Alembic.** Production's `init_db()` calls `Base.metadata.create_all()`, which creates missing tables but never alters existing ones. This works for additive changes (new tables, new models) but will fail silently the first time a column is added to an existing table. The `a27cap000008`, `000009`, `000010` migrations exist but are not run at boot.

Before the next non-additive schema change, the deployment entrypoint must switch to `alembic upgrade head`. This is a standalone task, not part of Phase 3.

## Build order

- **3.1–3.5** ✅ complete
- **3.6** — Extraction wire-up (next)
- **3.7** — UI
- **3.8** — Integration and hardening

Each phase ends with all tests passing and a commit. Do not proceed to the next phase until the current phase's acceptance criteria are independently verified by running the tests.

