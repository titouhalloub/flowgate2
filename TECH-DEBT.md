# Tech Debt

## Duplicated vesting math

Vesting math is duplicated. `src/services/flowgateEngine.ts` mirrors `app/captable.py`. Any formula change must be made in both files in the same commit. Long-term fix: route the dashboard's cap table reads through the backend and delete the client engine's vesting math.

(Flagged in both files — see the mirror notice at the top of `src/services/flowgateEngine.ts`.)

## Assistant prompt size

The assistant loads ~44k characters (~11k tokens) of markdown into every
system prompt. That's ~$0.10/question on Sonnet. At pilot scale, consider:
(a) trimming the curated file list, (b) chunking and retrieving only
relevant sections, or (c) a two-tier approach — a small knowledge base for
common questions, retrieval for the long tail. None of this is urgent for
a demo, but it caps unit economics at pilot scale.

## Frontend/backend severity naming mismatch

Frontend ComplianceFinding (src/types.ts) uses severity:
'blocking' | 'review' | 'advisory'. Backend RuleSeverity
(app/models/enums.py) uses 'blocking' | 'review' | 'info'. The third
member differs. Currently harmless because InstrumentOut has no
compliance_findings field and the frontend panel renders client-computed
stub data. Must be reconciled before the backend's real findings flow to
the UI.

## requirements.txt and pyproject.toml are out of sync

requirements.txt lists psycopg2-binary and openai; pyproject.toml
omits both. Production uses requirements.txt (Dockerfile). Local
dev uses the venv, which was built from requirements.txt. The two
files should be reconciled -- pyproject.toml is the canonical
source per PEP 621.

## LoadedRule docstring stale

app/compliance.py's LoadedRule docstring says "Row mode: arrives
in Phase 2.5f". Row mode shipped in ac0776d. Update the docstring
on the next pass through that file.

## Jurisdiction not exposed in UI

jurisdictions is persisted on Instrument and read automatically by
the document submission route. There is no UI to set or edit it --
it is only settable via the API's InstrumentCreate payload. Adding
a jurisdiction field to the instrument creation/edit UI is a later
sub-phase.

## Compliance rule editor: raw JSON condition input

The rule editor accepts `condition` as a raw JSON textarea.
Compliance officers who do not know JSON Logic cannot author a rule
without help. A structured builder (key/value rows, or an
evaluator-picker once the rule vocabulary stabilizes) is the eventual
fix. Documented here so the textarea is not mistaken for a finished
UX.

## Client-side cap-table engine still used by FlowgateDashboard

The cap-table snapshot for the Cap Table tab now comes from the API
(`GET /cap-table/{issuer}`), so the backend is the single source of
truth for that panel.

`FlowgateDashboard.tsx` still calls `computeCapTable` from
`src/services/flowgateEngine.ts` for its own demo mode (the
`demoCompanySetup` toggle with `before`/`after` Series A views).
That demo path is not connected to the API and operates on local
sample events.

To fully close this (the review's M2), either:
- replace the demo mode with a fetch from the API for a demo issuer,
- or delete the demo mode.

Until then, two implementations of vesting math exist in the codebase.
Any change to `app/captable.py`'s vesting math must be mirrored in
`flowgateEngine.ts` in the same commit -- the pre-existing note above
still applies to the FlowgateDashboard path.

## Shared API key maps to admin

The API key path in `app/auth.py` maps every configured key to
`role="admin"` unless the operator sets `A27_API_KEYS` to a JSON
object mapping keys to roles. The current dev/deploy key
(`development_key_123`) is admin.

Before any production onboarding:
- Replace with a JSON allowlist, one key per integration, each with
  the minimum role it needs.
- Rotate the dev key; do not ship a known-value key.

## ORM/migration drift on cap_table_events and instruments

The ORM models declare columns that no Alembic migration creates:
- cap_table_events: related_convertible_id, related_round_id, vesting_start_date,
  vesting_period_months, cliff_months, acceleration_clause, is_repurchase,
  repurchase_approver (8 columns)
- instruments: jurisdictions (JSON)

Local a27.db was built via create_all(), not migrations, so its schema is behind
the ORM. Production Neon likely has these columns (features work there), but this
needs verification before the next migration on production.

Consequence: alembic revision --autogenerate produces destructive noise until
this is reconciled. Every future migration requires hand-trimming. Specifically,
autogenerate proposes adding instruments.jurisdictions as NOT NULL with no server
default (fails on any table holding rows) and dropping the composite indexes
ix_webhook_deliveries_subscription and ix_webhook_subscriptions_active.

Fix (when there is time): write a deliberate migration that adds the missing
columns with proper server_defaults, verify against a copy of production schema,
then run alembic autogenerate cleanly.

## /cap-table/{issuer}/history is O(NxM)
Each snapshot calls compute_cap_table(), which re-queries and re-replays
events from scratch. With M<=24 boundaries and N<1000 events this is fine
(sub-100ms in practice). If an issuer with 10k+ events needs history,
refactor captable.py to expose a resumable accumulator that emits
snapshots at each boundary from a single pass.

## Local a27.db missing ORM-declared columns
Local SQLite (a27.db) was created via Base.metadata.create_all() at some
point, but the ORM has since gained columns that no migration created:
  - cap_table_events: related_convertible_id, related_round_id,
    vesting_start_date, vesting_period_months, cliff_months,
    acceleration_clause, is_repurchase, repurchase_approver
  - instruments: jurisdictions

Consequence: any local route that queries cap_table_events 500s with
"no such column". This blocks local smoke testing of /cap-table,
/cap-table/.../history, POST /cap-table-events, and anything else that
touches events. Tests pass because conftest runs create_all(), which
creates the missing columns in the test DB.

Production (Neon) has the columns, so this is a local-only problem.

Fix: drop a27.db and recreate it via `alembic upgrade head`, or run a
one-off ALTER TABLE migration against it. Or run the missing-columns
migration from the earlier "ORM/migration drift" entry above.

Not blocking for production deployments. Blocks local dev.

## tests/conftest.py client fixture breaks require_role-guarded routes
The `client` fixture overrides require_api_key with the bare string
"test-key-123". require_role (app/auth.py:248) dereferences user.role
on that string and raises AttributeError. Every seed route guarded by
require_role therefore fails in tests.

Effect: ~90 pre-existing test failures, none reflecting real bugs. New
test files work around this by using a separate fixture (client2 in
tests/test_compliance_dry_run.py, test_cap_table_history.py) that
overrides with a real AuthUser.

Fix: change the conftest override to return an AuthUser(role="admin",
id="test-user", auth_method="api_key"). Small, isolated, unblocks the
suite.
