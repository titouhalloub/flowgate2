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
