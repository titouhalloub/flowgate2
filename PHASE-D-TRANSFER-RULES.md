# Phase D — Transfer Rules & ROFR Engine (Design)

Status: APPROVED-FOR-IMPLEMENTATION (design doc first, per CAPITAL-CALL-PLAN.md)
Scope trigger: user go-ahead. Additive only — two new tables, no rewrites.

## Problem

Today any holder can be stripped of shares by a single `POST /cap-table-events`
with `event_type=transfer`: the endpoint checks existence and overdraft, but no
bylaw, right-of-first-refusal, or board approval stands between the request and
the event log. Phase D inserts an evaluation gate into that write path without
changing the event-sourcing replay (compute_cap_table stays untouched).

## Principles carried over from Phases A–C

- **Extraction prepares, a human disposes.** Rules never move shares; a named
  human approves or the gate blocks.
- **Derived, never stored.** Overdue/pending counts are computed at read time.
- **Named humans.** Every rule and every approval carries `created_by` /
  `reviewer` (same audit rule as capital-call review).
- **Fail closed.** Ambiguous rule state blocks; it never silently allows.

## Rule schema (condition / gate / approver / escalation)

```
transfer_rules:
  id                String(64) PK
  issuer_name       String(255)          # scope: all securities of the issuer
  rule_type         Enum(rofr | board_approval | bylaw_lockup)
  condition         JSON                  # typed per rule_type, see below
  gate              Enum(block | review)  # block=409 always; review=needs human
  approver          String(255)           # named role, e.g. "Board Secretary"
  escalation_role   String(255) nullable  # who it escalates to
  escalation_after_days  Int nullable     # pending review older than N days -> overdue
  active            Bool (default True)   # deactivation is additive, never delete
  created_by        String(64)            # named human
  created_at        DateTime
```

Condition payloads (validated on create, stored verbatim):

| rule_type | condition keys | meaning |
|---|---|---|
| `rofr` | `window_days: int` (optional, positive when present), `exempt_holder_ids: [str]` | transfers from non-exempt holders need ROFR; window_days is an advisory window |
| `board_approval` | `min_quantity: float` | transfers >= min_quantity need board approval |
| `bylaw_lockup` | `until_date: ISO datetime`, `holder_ids: [str]` | named holders cannot transfer before the date |

`condition` is opaque to the engine except for these keys — the engine reads
only what it knows; unknown keys are carried into the audit record verbatim
(so future rule types don't need a migration).

## Evaluation record (the second table)

```
transfer_evaluations:
  id                String(64) PK
  security_id       FK securities.id
  from_holder_id    FK investors.id
  holder_id         FK investors.id
  quantity          Float
  price_per_share   Float nullable
  effective_date    DateTime
  rules_evaluated   JSON      # [{rule_id, rule_type, gate, outcome}]
  outcome           Enum(allowed | blocked | review_required | approved | rejected)
  blocking_rule_id  String(64) nullable
  reviewer          String(64) nullable   # named human (approve/reject)
  reviewed_at       DateTime nullable
  created_at        DateTime
```

Every gate decision is an immutable audit row — allowed transfers get one too,
so "why was this transfer permitted" always has an answer.

## Evaluation point (the write path)

In `record_cap_table_event`, after the existence checks and only when
`event_type == TRANSFER` (cancellation/exercise/conversion out of scope for D1;
noted as D2 candidates):

1. `evaluate_transfer_rules(session, proposed)` runs all active rules scoped
   to the security's issuer against the proposed transfer.
2. `allowed` (no rules, or only exempt/conditions-not-triggered) -> write the
   event exactly as today, but also record the evaluation.
3. `blocked` (gate=block, or bylaw_lockup triggered) -> **409**, nothing
   written, evaluation row kept with `outcome=blocked` and the rule id.
4. `review_required` (gate=review) -> **409** with body
   `{"detail": ..., "evaluation_id": ...}`; nothing written. The named
   approver then resolves it:
   - `POST /transfer-evaluations/{id}/approve?reviewer=` -> writes the
     pre-validated transfer event (same overdraft replay check as the normal
     path) + ledger entry, outcome -> `approved`.
   - `POST /transfer-evaluations/{id}/reject?reviewer=` -> nothing written,
     outcome -> `rejected`, ledger entry records the rejection.
   Both endpoints **409 if the evaluation is not pending**, and the reviewer
   must be a non-empty named human (consistent with the capital-call gate).

## Read endpoints

- `GET  /transfer-rules?issuer_name=` — active + inactive, newest first.
- `POST /transfer-rules` — 400 on unknown rule_type / malformed condition;
  a new rule of the same rule_type for the same issuer SUPERSEDES (deactivates)
  the previous active one — history is kept, never deleted.
- `GET  /transfer-evaluations?outcome=pending` — review queue; each row carries
  derived `overdue` (pending AND created_at older than escalation_after_days,
  same derivation pattern as Phase B's overdue badge). No auto-escalation
  action in D1 — surfacing only, matching the plan's Phase B precedent.

## Ledger

The existing `LedgerEntryType` enum is string-valued in the DB
(`native_enum=False`), so adding a new `transfer_evaluation` value is additive
at the storage layer. Every gate outcome (allowed / blocked / approved /
rejected) appends exactly one `transfer_evaluation` ledger entry, keeping the
unified audit trail complete.

## Migration

`a27cap000007_transfer_rules.py` — additive, two tables, SQLite batch-mode,
nullable-safe, same convention as migrations 3–6.

## Tests (target ~12)

1. Rule create + validation (unknown type -> 400; malformed condition -> 400;
   window_days, when present, must be a positive int). Creating a second rule
   of the same type for the same issuer supersedes the first.
2. Transfer with no rules -> allowed, event written, evaluation recorded `allowed`.
3. `block` gate -> 409, event NOT written (cap table unchanged), evaluation `blocked`.
4. `review` gate -> 409 + evaluation pending -> approve -> event written (overdraft
   still enforced) -> status `approved`.
5. Reject -> event never written.
6. Double-approve / approve-after-reject -> 409.
7. Exempt holder (rofr `exempt_holder_ids`) -> allowed despite active rofr.
8. `board_approval` min_quantity: below -> allowed; above -> review.
9. `bylaw_lockup` before `until_date` -> blocked; after -> allowed.
10. Pending queue + derived `overdue` flag (escalation_after_days elapsed).
11. Deactivated rule -> transfer allowed.
12. Every gate outcome appended exactly one ledger entry.

## UI (minimal, Phase A-panel style)

New compact "Transfer Rules" section in the React dashboard: list rules per
issuer, create-rule form (type/condition/gate/approver), pending-evaluation
queue with approve/reject + overdue badge. Live-first, demo fallback preserved.

## Explicit non-goals (D1)

- No offer/counter-offer workflow, no holder-facing notification (ROFR window
  is recorded; the human confirms waivers at approve time).
- No automatic escalation execution (badge only).
- Cancellation / exercise / conversion gates (D2 candidates).
