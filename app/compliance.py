"""Compliance-as-configuration gateway.

The thesis being proven: **one gateway, pluggable rule sets** — never a fork.
``TRADITIONAL_RULES`` and ``ISLAMIC_RULES`` are both plain data
configurations fed through the *same* ``ComplianceGateway.evaluate`` code
path. Nothing in the gateway knows about Islam or KYC specifically; it just
runs the rule set it was handed and applies the same outcome logic:

- Any rule that produces a ``blocking`` finding  -> SYSTEM_FLAGGED_NONCOMPLIANT
- Otherwise, if a scholar review is warranted    -> PENDING_SCHOLAR_REVIEW
- Otherwise                                       -> NOT_APPLICABLE

The gateway can never set SCHOLAR_APPROVED / SCHOLAR_REJECTED — those remain
human-only (``app.review``). Every decision emits a Langfuse trace (console
backend in dev) with the inputs, rule set name, per-rule findings and the
outcome, and is persisted to the append-only ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Sequence
from uuid import uuid4

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.enums import (
    ComplianceMode,
    DocumentType,
    LedgerEntryType,
    RuleSeverity,
    ShariahReviewStatus,
)
from app.models.orm import Document, Instrument, LedgerEntry
from app.telemetry import get_tracer
from app.json_logic import evaluate as eval_json_logic


@dataclass
class RuleFinding:
    code: str
    severity: RuleSeverity
    message: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleContext:
    instrument: Instrument
    documents: Sequence[Document]
    documents_by_type: dict[DocumentType, list[Document]] = field(init=False)

    def __post_init__(self) -> None:
        self.documents_by_type = {}
        for doc in self.documents:
            self.documents_by_type.setdefault(doc.document_type, []).append(doc)


def build_context(
    instrument: Instrument,
    documents: Sequence[Document],
) -> dict:
    """Serialize (instrument, documents) into the plain dict that
    the JSON Logic evaluator consumes.

    Field selection follows the diagnostic: rules read exactly five
    instrument attributes, eight type_specific_data keys (four
    interest/profit keys plus the four gharar markers), and the
    document types in the batch. Nothing else is exposed. Keeping
    the surface minimal makes the JSON Logic expressions easy to
    audit and stops a misconfigured condition from reading state it
    was never meant to touch.

    Enum values are serialized to their string form so conditions
    can compare against literals like "loan" or "sukuk" instead of
    Python enum members.
    """
    tsd = instrument.type_specific_data or {}

    # Serialize only the eight keys any current rule reads. Adding a
    # key here is a deliberate act; anything else stays opaque.
    type_specific_data = {
        k: tsd.get(k)
        for k in (
            "interest_rate",
            "fixed_coupon",
            "profit_rate",
            "ijara_rental_rate",
            "leverage",
            "margin",
            "derivative",
            "future",
        )
    }

    shariah_contract_type = instrument.shariah_contract_type
    if shariah_contract_type is not None and hasattr(
        shariah_contract_type, "value"
    ):
        shariah_contract_type = shariah_contract_type.value

    compliance_mode = instrument.compliance_mode
    if hasattr(compliance_mode, "value"):
        compliance_mode = compliance_mode.value

    transaction_type = instrument.transaction_type
    if hasattr(transaction_type, "value"):
        transaction_type = transaction_type.value

    documents_by_type: dict[str, list[dict]] = {}
    for doc in documents:
        doc_type = doc.document_type
        key = doc_type.value if hasattr(doc_type, "value") else doc_type
        documents_by_type.setdefault(key, []).append({"id": doc.id})

    return {
        "instrument": {
            "transaction_type": transaction_type,
            "compliance_mode": compliance_mode,
            "shariah_contract_type": shariah_contract_type,
            "underlying_asset_id": instrument.underlying_asset_id,
            "underlying_asset_description": (
                instrument.underlying_asset_description
            ),
            "type_specific_data": type_specific_data,
        },
        "documents_by_type": documents_by_type,
    }


Rule = Callable[[RuleContext], list[RuleFinding]]

@dataclass(frozen=True)
class LoadedRule:
    """A single compliance rule as the loader hands it to the engine.

    The shape after Phase 2.5e. Two emission modes coexist during
    the migration:

    - Callable mode: `callable` is a Python function that inspects
      the RuleContext and returns findings. Authoritative today for
      every rule. Constants and every DB row whose rule_name has a
      matching Python function use this path.
    - Row mode: arrives in Phase 2.5f. The engine will iterate
      `rows`, evaluate each row's condition, and emit findings from
      the row's finding_code/severity/message.

    Fields:
        name: stable identifier, matches ComplianceRule.rule_name.
        callable: the Python function that decides which finding to
            emit. Optional; None means row-driven emission.
        applies_to: TransactionType string values this rule applies
            to. Empty list means "all instrument types".
        condition: JSON Logic expression gating when the rule runs.
            Empty dict means no gate.
        rows: one dict per DB row sharing this rule_name. Each dict
            carries {condition, applies_to, finding_code, severity,
            message_template}. Empty for constant-defined rules.
        mode: "callable" -- rule.callable(ctx) runs and produces
            findings. "row" -- engine iterates rule.rows and emits one
            finding per row whose condition evaluates true. Defaults
            to "callable" so every constant and every row whose
            condition is still {} takes the pre-2.5f path.
    """
    name: str
    callable: Rule | None
    applies_to: list[str]
    condition: dict[str, Any] = field(default_factory=dict)
    rows: list[dict[str, Any]] = field(default_factory=list)
    mode: str = "callable"


@dataclass
class ComplianceDecision:
    rule_set_name: str
    compliance_mode: ComplianceMode
    outcome: ShariahReviewStatus  # system-set status only
    findings: list[RuleFinding] = field(default_factory=list)

    @property
    def blocking(self) -> bool:
        return any(f.severity == RuleSeverity.BLOCKING for f in self.findings)


# ---------------------------------------------------------------------------
# Rule set registry — the configuration surface
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Rule set registry — the configuration surface
# ---------------------------------------------------------------------------


# Frozen data mirror of the DB seed (migration a27cap000012 +
# a27cap000013). Used as a fallback when no session is available
# (unit tests that exercise engine mechanics directly) and when the
# compliance_rules table is empty on first boot. Every entry is in
# row mode with callable=None -- the engine emits findings from the
# rows list, using the same JSON Logic conditions the DB seed
# stores. Kept in sync with the migrations by hand; a divergence
# test in test_compliance_seed.py catches drift.
TRADITIONAL_RULES: list[LoadedRule] = [
    LoadedRule(
        name="kyc_aml_present",
        callable=None,
        applies_to=[],
        condition={"empty": [{"var": "documents_by_type.kyc"}]},
        rows=[{
            "applies_to": [],
            "condition": {"empty": [{"var": "documents_by_type.kyc"}]},
            "finding_code": "TRAD_KYC_MISSING",
            "severity": RuleSeverity.BLOCKING,
            "message_template": "No KYC/AML document attached to the instrument.",
        }],
        mode="row",
    ),
    LoadedRule(
        name="interest_rate_sanity",
        callable=None,
        applies_to=[],
        condition={},
        rows=[
            {
                "applies_to": [],
                "condition": {"empty": [
                    {"var": "instrument.type_specific_data.interest_rate"},
                ]},
                "finding_code": "TRAD_RATE_MISSING",
                "severity": RuleSeverity.REVIEW,
                "message_template": (
                    "No interest_rate on record; cannot apply sanity bounds."
                ),
            },
            {
                "applies_to": [],
                "condition": {"and": [
                    {"!": {"empty": [
                        {"var": "instrument.type_specific_data.interest_rate"},
                    ]}},
                    {"!": {"in_range": [
                        {"var": "instrument.type_specific_data.interest_rate"},
                        0.0, 0.30,
                    ]}},
                ]},
                "finding_code": "TRAD_RATE_OUT_OF_BAND",
                "severity": RuleSeverity.BLOCKING,
                "message_template": (
                    "Interest rate outside acceptable band [0, 0.30]."
                ),
            },
        ],
        mode="row",
    ),
    LoadedRule(
        name="mode_info",
        callable=None,
        applies_to=[],
        condition={"==": [1, 1]},
        rows=[{
            "applies_to": [],
            "condition": {"==": [1, 1]},
            "finding_code": "TRAD_MODE_INFO",
            "severity": RuleSeverity.INFO,
            "message_template": (
                "Instrument evaluated under traditional track."
            ),
        }],
        mode="row",
    ),
]

ISLAMIC_RULES: list[LoadedRule] = [
    LoadedRule(
        name="contract_type_declared",
        callable=None,
        applies_to=[],
        condition={"in": [
            {"var": "instrument.shariah_contract_type"},
            [None, "none"],
        ]},
        rows=[{
            "applies_to": [],
            "condition": {"in": [
                {"var": "instrument.shariah_contract_type"},
                [None, "none"],
            ]},
            "finding_code": "SHAR_CONTRACT_TYPE_MISSING",
            "severity": RuleSeverity.BLOCKING,
            "message_template": (
                "Islamic instrument is missing a declared Shariah "
                "contract type."
            ),
        }],
        mode="row",
    ),
    LoadedRule(
        name="asset_backing",
        callable=None,
        applies_to=[],
        condition={},
        rows=[
            {
                "applies_to": [],
                "condition": {"and": [
                    {"empty": [
                        {"var": "instrument.underlying_asset_description"},
                    ]},
                    {"empty": [
                        {"var": "instrument.underlying_asset_id"},
                    ]},
                ]},
                "finding_code": "SHAB_ASSET_BACKING_MISSING",
                "severity": RuleSeverity.BLOCKING,
                "message_template": (
                    "Islamic instrument has no underlying asset "
                    "description or ID."
                ),
            },
            {
                "applies_to": [],
                "condition": {"or": [
                    {"!": {"empty": [
                        {"var": "instrument.underlying_asset_description"},
                    ]}},
                    {"!": {"empty": [
                        {"var": "instrument.underlying_asset_id"},
                    ]}},
                ]},
                "finding_code": "SHAB_ASSET_PRESENT",
                "severity": RuleSeverity.INFO,
                "message_template": (
                    "Underlying asset is declared for the Islamic "
                    "instrument."
                ),
            },
        ],
        mode="row",
    ),
    LoadedRule(
        name="no_fixed_interest",
        callable=None,
        applies_to=[],
        condition={},
        rows=[
            {
                "applies_to": [],
                "condition": {"or": [
                    {"!": {"empty": [
                        {"var": "instrument.type_specific_data.interest_rate"},
                    ]}},
                    {"==": [
                        {"var": "instrument.type_specific_data.fixed_coupon"},
                        True,
                    ]},
                ]},
                "finding_code": "SHAB_FIXED_INTEREST",
                "severity": RuleSeverity.BLOCKING,
                "message_template": (
                    "Fixed interest / fixed coupon detected on the "
                    "Islamic track."
                ),
            },
            {
                "applies_to": [],
                "condition": {"!": {"or": [
                    {"!": {"empty": [
                        {"var": "instrument.type_specific_data.interest_rate"},
                    ]}},
                    {"==": [
                        {"var": "instrument.type_specific_data.fixed_coupon"},
                        True,
                    ]},
                ]}},
                "finding_code": "SHAB_NO_FIXED_INTEREST",
                "severity": RuleSeverity.INFO,
                "message_template": (
                    "No fixed-interest indicators found in "
                    "type_specific_data."
                ),
            },
        ],
        mode="row",
    ),
    LoadedRule(
        name="fatwa_reference",
        callable=None,
        applies_to=[],
        condition={},
        rows=[
            {
                "applies_to": [],
                "condition": {"empty": [{"var": "documents_by_type.fatwa"}]},
                "finding_code": "SHAB_FATWA_REFERENCE_MISSING",
                "severity": RuleSeverity.BLOCKING,
                "message_template": (
                    "No FATWA document attached; cannot route for "
                    "scholar review."
                ),
            },
            {
                "applies_to": [],
                "condition": {"!": {"empty": [
                    {"var": "documents_by_type.fatwa"},
                ]}},
                "finding_code": "SHAB_FATWA_REFERENCE_PRESENT",
                "severity": RuleSeverity.INFO,
                "message_template": (
                    "Fatwa document(s) attached for the scholar."
                ),
            },
        ],
        mode="row",
    ),
    LoadedRule(
        name="no_speculation",
        callable=None,
        applies_to=[],
        condition={"or": [
            {"meaningful": {"var": "instrument.type_specific_data.leverage"}},
            {"meaningful": {"var": "instrument.type_specific_data.margin"}},
            {"meaningful": {"var": "instrument.type_specific_data.derivative"}},
            {"meaningful": {"var": "instrument.type_specific_data.future"}},
        ]},
        rows=[{
            "applies_to": [],
            "condition": {"or": [
                {"meaningful": {"var": "instrument.type_specific_data.leverage"}},
                {"meaningful": {"var": "instrument.type_specific_data.margin"}},
                {"meaningful": {"var": "instrument.type_specific_data.derivative"}},
                {"meaningful": {"var": "instrument.type_specific_data.future"}},
            ]},
            "finding_code": "SHAB_GHARAR_INDICATOR",
            "severity": RuleSeverity.BLOCKING,
            "message_template": (
                "Instrument exhibits potential speculative indicators."
            ),
        }],
        mode="row",
    ),
]

RULE_SETS: dict[str, list[LoadedRule]] = {
    ComplianceMode.TRADITIONAL.value: TRADITIONAL_RULES,
    ComplianceMode.ISLAMIC.value: ISLAMIC_RULES,
}


def load_rule_sets(
    session,
    as_of: date | None = None,
) -> dict[str, list[LoadedRule]]:
    """Load rule sets from the database, falling back to the module
    constants when the table is empty.

    The database is the source of truth once populated: which rules
    run for a package is decided by the presence of active rows for
    that package. The callable that a row wraps is looked up by
    rule_name from the module constants -- Phase 2.5 replaces this
    with JSON Logic evaluation.

    Args:
        session: SQLAlchemy Session. If None, returns the constants
            directly (used by tests that construct the gateway
            without a database).
        as_of: the evaluation date. Defaults to today. Rows with
            effective_from > as_of or effective_to <= as_of are
            excluded. Among rows sharing a (package_name, rule_name),
            the row with the latest effective_from and version wins
            (used for the LoadedRule.condition and applies_to).

    Returns:
        dict[str, list[NamedRule]] -- same shape as RULE_SETS, keyed
        by package name (matching ComplianceMode.value for the two
        built-in packages).
    """
    from datetime import date as _date
    if as_of is None:
        as_of = _date.today()

    if session is None:
        return RULE_SETS

    from app.models.orm import ComplianceRule

    rows = (
        session.query(ComplianceRule)
        .filter(
            ComplianceRule.active.is_(True),
            ComplianceRule.effective_from <= as_of,
            or_(
                ComplianceRule.effective_to.is_(None),
                ComplianceRule.effective_to > as_of,
            ),
        )
        .order_by(
            ComplianceRule.effective_from.desc(),
            ComplianceRule.version.desc(),
        )
        .all()
    )
    if not rows:
        # Table empty: fall back to the compiled-in rule sets. This is
        # the state until Phase 2.3 seeds the table.
        return RULE_SETS

    # Build a lookup of every callable the module knows about, keyed by
    # its rule_name. A row whose rule_name has no matching callable is
    # skipped (and will be logged once a logger is added in a later
    # phase).
    legacy_by_name: dict[str, Callable[[RuleContext], list[RuleFinding]]] = {}
    for rules in RULE_SETS.values():
        for rule in rules:
            legacy_by_name[rule.name] = rule.callable

    # Multiple rows can share a rule_name (one per finding the rule can
    # emit). The callable is the same for all of them, and it decides
    # internally which finding to produce from the instrument. Dedup by
    # name so each callable runs exactly once per evaluation.
    # Group rows by (package_name, rule_name), deduplicating.
    # Rows sharing a rule_name have identical applies_to lists -- the
    # first one seen wins; the seed guarantees consistency.
    # Multiple rows can share a rule_name (one per finding the rule can
    # emit). The callable is the same for all of them, and it decides
    # internally which finding to produce. Dedup by rule_name so each
    # callable runs exactly once per evaluation. The first row's
    # condition and applies_to are used -- the seed guarantees
    # consistency across rows that share a name.
    grouped: dict[str, dict[str, list[dict]]] = {}
    for row in rows:
        bucket = grouped.setdefault(row.package_name, {})
        bucket.setdefault(row.rule_name, []).append({
            "applies_to": list(row.applies_to) if row.applies_to else [],
            "condition": dict(row.condition) if row.condition else {},
            "finding_code": row.finding_code,
            "severity": row.severity,
            "message_template": row.message,
        })

    result: dict[str, list[LoadedRule]] = {}
    for package, by_name in grouped.items():
        rules: list[LoadedRule] = []
        for name, row_metas in by_name.items():
            fn = legacy_by_name.get(name)
            # First row's metadata is the "primary" for the rule --
            # applies_to and condition are read by the current engine.
            # The full rows list carries every sibling row's metadata
            # for Phase 2.5f's row-driven emission.
            first = row_metas[0]
            # Row mode when every row for this rule_name carries a real
            # (non-empty) condition. The presence of a condition is the
            # migration marker: filling one in means the row is ready to
            # emit its own finding. A rule_name with any ungated sibling
            # falls back to callable mode, so a partial rollout degrades
            # cleanly.
            #
            # Constants have no rows and stay in callable mode. Every
            # DB row currently seeded by migration a27cap000012 has
            # condition={}, so this change is a no-op until
            # a27cap000013 fills them in.
            all_gated = (
                len(row_metas) > 0
                and all(bool(r.get("condition")) for r in row_metas)
            )
            mode = "row" if all_gated else "callable"
            rules.append(LoadedRule(
                name=name,
                callable=fn,
                applies_to=first["applies_to"],
                condition=first["condition"],
                rows=row_metas,
                mode=mode,
            ))
        if rules:
            result[package] = rules
    return result


# ---------------------------------------------------------------------------
# Gateway
# ---------------------------------------------------------------------------


class ComplianceGateway:
    """One code path; the rule set is the only variable."""

    def __init__(self, rule_sets: dict[str, list[NamedRule]] | None = None):
        self.rule_sets = rule_sets or RULE_SETS

    def evaluate(
        self,
        instrument: Instrument,
        documents: Sequence[Document],
        rule_set_name: str | None = None,
        extra_jurisdictions: list[str] | None = None,
    ) -> ComplianceDecision:
        """Run every rule in the set for the instrument's compliance mode.

        Outcomes are system-set only:
        - blocking finding  -> SYSTEM_FLAGGED_NONCOMPLIANT
        - otherwise         -> PENDING_SCHOLAR_REVIEW (Islamic)
                               or NOT_APPLICABLE (traditional)
        Never SCHOLAR_APPROVED / SCHOLAR_REJECTED.

        When ``extra_jurisdictions`` is provided, rules from every named
        package present in ``self.rule_sets`` are evaluated alongside the
        mode's package, and the findings merge into one decision. A
        package name that is not present in ``self.rule_sets`` is skipped
        and reported as an INFO finding with code
        ``JURISDICTION_NOT_LOADED``, so the caller can see which
        jurisdictions were unloadable without the evaluation failing.
        """
        mode = instrument.compliance_mode

        # Determine which packages to evaluate.
        # Primary selection: explicit rule_set_name, else the mode.
        # Then every extra jurisdiction that exists in self.rule_sets.
        primary = rule_set_name or mode.value
        packages: list[str] = []
        if primary in self.rule_sets:
            packages.append(primary)
        missing: list[str] = []
        if extra_jurisdictions:
            for j in extra_jurisdictions:
                if j == primary:
                    continue
                if j in self.rule_sets:
                    packages.append(j)
                else:
                    missing.append(j)

        # Collect the union of every package's rules, in order.
        rules: list[LoadedRule] = []
        for pkg in packages:
            rules.extend(self.rule_sets[pkg])

        ctx = RuleContext(instrument=instrument, documents=documents)
        findings: list[RuleFinding] = []

        # Condition gate (Phase 2.5d). When a LoadedRule carries a
        # non-empty condition, evaluate it against a JSON Logic context
        # derived from the instrument and documents. If it returns
        # False, the rule is skipped -- its callable does not run. An
        # empty condition means no gate (the callable is authoritative,
        # matching pre-2.5d behavior).
        #
        # The context is built lazily so engines with no gated rules
        # pay nothing.
        json_context: dict | None = None

        tt = instrument.transaction_type
        tt_value = tt.value if hasattr(tt, "value") else tt

        for rule in rules:
            if rule.applies_to and tt_value not in rule.applies_to:
                continue

            if rule.mode == "row":
                # Row-driven emission (Phase 2.5f). Each row carries
                # its own condition and finding metadata. A row whose
                # condition is empty is skipped -- row mode never
                # emits unconditionally.
                for row in rule.rows:
                    row_condition = row.get("condition") or {}
                    if not row_condition:
                        continue
                    if json_context is None:
                        json_context = build_context(instrument, documents)
                    if not eval_json_logic(row_condition, json_context):
                        continue
                    findings.append(RuleFinding(
                        code=row["finding_code"],
                        severity=row["severity"],
                        message=row["message_template"],
                    ))
                continue

            # Callable mode (default). Existing gate + callable.
            if rule.condition:
                if json_context is None:
                    json_context = build_context(instrument, documents)
                if not eval_json_logic(rule.condition, json_context):
                    continue
            if rule.callable is not None:
                findings.extend(rule.callable(ctx))

        # Report any jurisdiction the caller asked for that we could
        # not load. This surfaces configuration mistakes without
        # failing the evaluation.
        for name in missing:
            findings.append(RuleFinding(
                code="JURISDICTION_NOT_LOADED",
                severity=RuleSeverity.INFO,
                message=(
                    f"Requested jurisdiction {name!r} has no rule set "
                    "loaded; skipped."
                ),
            ))

        # Recompute blocking after appending the missing-jurisdiction
        # INFO findings (INFO never flips the outcome, but the merge
        # keeps a single computation point).
        blocking = any(
            f.severity == RuleSeverity.BLOCKING for f in findings
        )
        if mode == ComplianceMode.ISLAMIC:
            outcome = (
                ShariahReviewStatus.SYSTEM_FLAGGED_NONCOMPLIANT
                if blocking
                else ShariahReviewStatus.PENDING_SCHOLAR_REVIEW
            )
        else:
            outcome = (
                ShariahReviewStatus.SYSTEM_FLAGGED_NONCOMPLIANT
                if blocking
                else ShariahReviewStatus.NOT_APPLICABLE
            )

        return ComplianceDecision(
            rule_set_name="+".join(packages) if packages else primary,
            compliance_mode=mode,
            outcome=outcome,
            findings=findings,
        )


gateway = ComplianceGateway()


def run_gateway_with_ledger(
    session: Session,
    instrument: Instrument,
    documents: Sequence[Document],
    rule_set_name: str | None = None,
    trace_id: str | None = None,
    extra_jurisdictions: list[str] | None = None,
) -> ComplianceDecision:
    """Evaluate, persist the outcome on the instrument and write a ledger row.

    *Never* sets SCHOLAR_APPROVED — enforced by the ORM validates guard even
    if a bug tries.
    """
    decision = gateway.evaluate(
        instrument,
        documents,
        rule_set_name,
        extra_jurisdictions=extra_jurisdictions,
    )
    trace = get_tracer().span(
        "compliance.gateway",
        rule_set=decision.rule_set_name,
        instrument_id=instrument.id,
        compliance_mode=instrument.compliance_mode.value,
    )
    trace.finish(
        {
            "outcome": decision.outcome.value,
            "blocking": decision.blocking,
            "findings": [
                {"code": f.code, "severity": f.severity.value, "message": f.message}
                for f in decision.findings
            ],
        },
        confidence=1.0,  # deterministic rule engine — confidence is structural
        model="rule-engine/v1",
        rule_set=decision.rule_set_name,
        compliance_mode=instrument.compliance_mode.value,
    )
    trace.emit()

    instrument.shariah_review_status = decision.outcome
    session.add(
        LedgerEntry(
            id=str(uuid4()),
            entry_type=LedgerEntryType.COMPLIANCE_EVENT,
            instrument_id=instrument.id,
            document_id=next((d.id for d in documents), None),
            trace_id=trace_id or trace._trace.trace_id,
            payload={
                "event": "compliance_gateway",
                "rule_set": decision.rule_set_name,
                "outcome": decision.outcome.value,
                "findings": [
                    {"code": f.code, "severity": f.severity.value, "message": f.message}
                    for f in decision.findings
                ],
            },
        )
    )
    session.commit()
    return decision