# AI Assistant and Compliance Configuration — Combined Plan

This document is the source of truth for two connected pieces of the
Flowgate roadmap:

1. **The compliance configuration layer** — what exists today, and what
   Phase 2 would add to make compliance rules customer-editable.
2. **The read-only help assistant** — a chat interface that explains how
   the app works, grounded in the app's own documentation and the
   current state of the ledger.

Neither piece is built. This document describes what is real and what is
planned, so that no one — human or AI — accidentally claims a capability
that does not exist.

Every code reference in this document has been verified against the
repo. Where a capability is claimed, the file and line are named.

---

## Part 1 — Current State

### 1.1 The compliance engine

`app/compliance.py` implements `ComplianceGateway.evaluate(instrument,
documents, rule_set_name=None)`. The method iterates a list of rules,
evaluates each against the instrument, and returns an outcome with a
list of findings and a `ShariahReviewStatus`.

Two rule sets ship today, both as module-level Python constants in the
same file:

- `TRADITIONAL_RULES` — 3 rules: KYC/AML presence, interest rate sanity
  bounds, mode info.
- `ISLAMIC_RULES` — 5 rules: asset-backing declared, no fixed interest
  (riba), no speculation (gharar), fatwa reference present, contract
  type declared.

Both rule sets flow through the **identical** `evaluate()` code path.
The only thing that differs is which list is passed in. This is the
architectural claim: **one engine, multiple rule sets, no forked logic.**

### 1.2 Rule structure

Rules are **callables**, not data records. `app/compliance.py:65-68`:

```python
Rule = Callable[[RuleContext], list[RuleFinding]]
NamedRule = tuple[str, Rule]
```

A `NamedRule` is a `(name, callable)` tuple. The name string serves as
the rule's identifier. When the callable runs, it returns a list of
`RuleFinding` objects — and it is the finding, not the rule, that
carries the severity and message. `app/compliance.py:45-50`:

```python
@dataclass
class RuleFinding:
    code: str
    severity: RuleSeverity
    message: str
    detail: dict[str, Any] = field(default_factory=dict)
```

So the rule's severity is decided **inside** the callable, per
evaluation. A rule that inspects an instrument and returns a
`RuleFinding` with `severity=BLOCKING` produces a different outcome
than one that returns `severity=REVIEW`. The same rule could, in
principle, emit different severities for different instruments.

### 1.3 Outcome semantics

`app/compliance.py:337-350` computes the final `ShariahReviewStatus`
from the findings. The rules are:

- **Any `BLOCKING` finding, on either track** → `SYSTEM_FLAGGED_NONCOMPLIANT`.
- **Islamic track, non-blocking** → `PENDING_SCHOLAR_REVIEW`. This is the
  mode default, not something triggered specifically by `REVIEW`
  findings — an Islamic evaluation with zero findings also lands in
  `PENDING_SCHOLAR_REVIEW`.
- **Traditional track, non-blocking** → `NOT_APPLICABLE`. Traditional
  evaluations never produce `PENDING_SCHOLAR_REVIEW`.

The asymmetry is deliberate. The Islamic track's default posture is
"nothing ships without a human sign-off." The traditional track's
default is "nothing special to do unless a rule fires."

### 1.4 No-self-certification at the ORM layer

`app/models/orm.py` enforces two validators, one on `Instrument`
(lines 155–171) and one on `Document` (lines 239–251). Both check
whether the value being written is in a `HUMAN_ONLY` set containing
`SCHOLAR_APPROVED` and `SCHOLAR_REJECTED`, and both raise
`ShariahReviewValidationError` — a `ValueError` subclass defined at
`orm.py:89` — when a system path attempts to write a human-only value.

The error message names the constraint explicitly:

```
Cannot set {value!r} on Instrument {self.id!r} outside an explicit
human review endpoint (reviewer_id required).
```

The only path that reaches those states is
`app/review.submit_human_review_instrument` /
`submit_human_review_document`, which use a deliberate Core `update()`
call that bypasses the validator. That bypass is intentional and
auditable — it exists precisely so that one function is the only place
in the codebase where a human-certified status can be written.

### 1.5 Observability — Langfuse backend exists, disabled by default

`app/telemetry.py` contains a complete `LangfuseTracer` backend. It
lazily imports the Langfuse client and forwards every trace —
generation, events, usage, cost — to a configured instance.

`app/config.py:32-36` ships the required settings:

```python
langfuse_public_key: str = ""
langfuse_secret_key: str = ""
langfuse_host: str = "https://cloud.langfuse.com"
telemetry_backend: str = "console"
```

`langfuse>=2.30` is in `requirements.txt`. The default backend is
`console`, which writes trace records to **stderr** (not stdout).
Switching `telemetry_backend` to `langfuse` and providing the three
keys enables full Langfuse tracing with no code changes.

**The truthful claim is:** a Langfuse backend is built and available;
the default sink is the console. Production use would flip the setting.

### 1.6 What is not built

- **Rules are not in the database.** They are Python `(name, callable)`
  tuples. Adding a rule is a code change.
- **No rule editor UI.** No screen lists, edits, or versions rules.
- **No rule composition.** A DIFC fund with a Cayman master cannot load
  both rule sets simultaneously.
- **No RAG or knowledge base.** No vector store, no embeddings, no
  retrieval layer.
- **No assistant or chat interface.** There is no natural-language
  surface anywhere in the app.

## Part 2 — Compliance Configuration (Phase 2)

Making compliance rules customer-editable requires the following work.
Estimates are working days for a single engineer.

### 2.1 Rules as database rows (2 days)

New model `ComplianceRule`:

- `id` (UUID, primary key)
- `package_name` (string) — `DIFC`, `ISLAMIC`, `TRADITIONAL`
- `jurisdiction` (string) — `AE-DIFC`, `SA`, `KY`
- `version` (integer)
- `effective_from` (date)
- `effective_to` (date, nullable)
- `rule_name` (string) — the identifier from the current tuple form
- `name` (string) — human-readable label
- `severity` (enum) — `BLOCKING`, `REVIEW`, `INFO`
- `applies_to` (JSON list)
- `condition` (JSON) — JSON Logic expression
- `message` (string)
- `created_by` (string)
- `created_at` (datetime)

A migration seeds the existing `TRADITIONAL_RULES` and `ISLAMIC_RULES`
as rows in this table. The severity and message move from the callable
into the row — the callable's role narrows to evaluating a condition.

### 2.2 Package loader (1 day)

`load_rules(jurisdiction: str, as_of: date) -> list[NamedRule]` queries
the table for rows where `effective_from <= as_of` and
(`effective_to IS NULL` or `effective_to > as_of`), and returns them in
the same `(name, callable)` shape the current engine consumes. The
gateway signature does not change.

### 2.3 JSON Logic conditions (3 days)

Replace the condition-checking bodies inside the callables with JSON
Logic expressions. Add `json-logic-py` (Python) and `json-logic-js`
(TypeScript) so the same rule evaluates identically in both
environments. The rule's `severity` and `message` come from the row,
not from inside the callable.

### 2.4 Rule composition (1 day)

`load_composite_rules(jurisdictions: list[str], as_of: date)` loads all
rules for all requested jurisdictions and concatenates them. A
`BLOCKING` finding from any jurisdiction flags the instrument.

### 2.5 Rule editor UI (5 days)

New screen on the Compliance tab:

- Table listing rules for the selected jurisdiction and version
- Inline edit for name, severity, message, condition
- Save creates a new version row
- Old version's `effective_to` is set to today minus one day
- Every save writes a ledger entry
- A "view findings" panel shows which rules fired on a past evaluation

### 2.6 Four-eyes approval for rule changes (2 days)

Two-step approval. A compliance officer proposes, a second approves.
Same pattern as the cap table proposal gate.

### Phase 2 total

14 working days, plus buffer. Roughly 3 weeks for one engineer.

## Part 3 — The Read-Only Help Assistant

### 3.1 What it is

A chat panel that answers questions about how the app works, grounded in
the app's own documentation and the current state of the ledger.

### 3.2 What it is not

- **Not an ops agent.** Cannot create proposals, approve conversions,
  edit rules, or write anything.
- **Not a compliance decision-maker.** Never says "this is compliant"
  or "approve this." Explains what the gateway found and what the next
  step is.
- **Not a general assistant.** Answers questions about Flowgate, and
  only Flowgate.

### 3.3 Why it matters

The domain is hard. A first-time user looking at the Convertibles panel
doesn't know what "outstanding" means, why a proposal needs approval,
or what a cap price is. The assistant explains these in context.

Questions it should answer well:

- *"Why is this document in review?"* → reads the extraction
  confidence, names the fields the extractor couldn't find
- *"What's a convertible?"* → explains the SAFE-off-cap-table model
- *"What happens when I approve this proposal?"* → describes the
  resulting write, without executing it
- *"What does the 409A badge mean?"* → "a round just committed, the FMV
  may be stale, it's a nudge"
- *"Which compliance rules are loaded right now?"* → reads the current
  rule set for the issuer
- *"Why did this get flagged?"* → reads the findings from the most
  recent evaluation and explains each one

### 3.4 Architecture

**Backend:** `POST /assistant/ask` taking
`{question: str, issuer_name: str | null}`. The endpoint:

1. Loads the knowledge base — a `docs/assistant/` folder of markdown
   files kept in the repo
2. Loads current context — the issuer's cap table, proposals,
   convertibles, recent ledger entries, and loaded compliance rules
3. Sends the question plus context to Claude via the existing OpenRouter
   integration (`app/classification.py:536-677` is the working example
   of the same client pattern)
4. Returns the answer plus source references

**Knowledge base:** plain markdown files in the repo. No vector store.
RAG is overkill for an app this size.

**Guardrails in the system prompt:**

- Answer only from the provided context
- Never claim compliance; never suggest an approval decision
- Never suggest executing an action — describe the click instead
- When the answer is not in context, say so explicitly
- Cite the source of every answer — plan file, ledger entry ID,
  document ID, or UI panel name

**Frontend:** a floating chat panel on the Cap Table tab. Empty state
shows three example questions as clickable chips.

**Testing:** the same eval harness pattern as the rest of the app. A
test suite with 15–20 question/answer pairs. If the model hallucinates
app behavior, the eval catches it. Logs go through `app/telemetry.py`
like everything else — which means they can be traced to Langfuse when
that backend is enabled, or to the console by default.

### 3.5 What the assistant cannot say

| Question from user | Must not say | May say |
|---|---|---|
| "Is this document compliant?" | "Yes" / "No" | "The gateway flagged X and Y. A reviewer decides." |
| "Can I approve this?" | "Yes" | "Approval requires a named reviewer. Here's what the gateway found." |
| "What's the tax treatment?" | Any specific answer | "I don't have information about that in the app." |
| "Should I invest in this fund?" | Any advice | "I can only help with questions about the Flowgate app." |

### 3.6 Scope

**In:** read-only FAQ and current-state questions, grounded in
`docs/assistant/` and the current ledger, one endpoint, one panel, one
system prompt, an eval suite.

**Out:** any write action, any compliance decision, any "chat with your
documents," any RAG, multi-turn state, session memory.

### 3.7 Estimate

4 days total — 2 for the endpoint and prompt engineering, 1 for the
frontend panel, 1 for eval iteration.

## Part 4 — How They Connect

### 4.1 The assistant explains the compliance layer

Once Phase 2 ships and rules are customer-editable, the assistant
becomes the way users understand what their rules do: which rules are
loaded, what changed in the last update, why a rule fired on this
instrument but not the previous one.

The assistant reads the rule table, not the code. When rules are
database-backed, the assistant's grounding becomes dynamic.

### 4.2 The compliance layer respects the assistant's boundary

The assistant never certifies compliance. The rule engine never
certifies compliance. Only a human reviewer does. The two systems
enforce the same invariant from different angles:

| System | Enforces | Method |
|---|---|---|
| Compliance engine | Cannot self-certify | ORM validators on `shariah_review_status` |
| Assistant | Cannot claim compliance | System prompt + eval suite |

Both are structural. Neither relies on the user to behave well.

### 4.3 The coherence rule

**Anything the assistant can explain, the compliance engine can prove.**
The assistant cites the rule name; the engine has the rule. The
assistant cites the ledger entry; the ledger has the entry. There is no
"the assistant said so."

---

## Part 5 — Build Order

| Order | Work | Why first | Estimate |
|---|---|---|---|
| 1 | Unify issuer selection across panels | The assistant will be confused by wrong-issuer data. Today the code uses `issuerName` props and an `ISSUER_NAME` constant (`CapTableView.tsx:1134`); there is no shared issuer state. | Half day |
| 2 | Smoke test script | Prevents the class of bug that has dominated recent sessions | 2 hours |
| 3 | Extraction robustness (smart quotes, LaTeX delimiters, inline money) | Groundwork for the assistant to answer "why did extraction fail?" | Half day |
| 4 | **Read-only help assistant** | Zero risk, high visibility, immediately demoable | 4 days |
| 5 | Compliance config Phase 2 | Requires the assistant to explain the new surface | 3 weeks |

Steps 1–3 are cleanup. Step 4 is the new product. Step 5 is the new
infrastructure.

Do not reorder. The assistant built before step 3 will spend its time
explaining extraction bugs instead of features. Phase 2 built before
the assistant will produce a rule editor nobody understands.

---

## Part 6 — What This Document Does Not Claim

Flowgate does not have:

- RAG, vector retrieval, or a compliance knowledge base
- A customer-editable rules engine
- A chat assistant or any natural-language interface
- Arabic-language compliance rules or UI
- Any write-capable AI agent

Flowgate **does** have a Langfuse tracing backend, currently disabled
by default (`telemetry_backend = "console"`). Enabling it requires
setting the backend to `"langfuse"` and providing the three keys.

Anything described in Parts 2 and 3 is planned. Anything described in
Part 1 is built.

The distinction matters. Every claim made about this product should be
traceable to a file, a commit, or a running endpoint. If a capability
is described in a pitch deck but not in this document, it does not exist.




