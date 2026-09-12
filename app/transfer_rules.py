"""Phase D -- transfer rules / ROFR engine.

Design: ``PHASE-D-TRANSFER-RULES.md``. The engine evaluates all active
rules scoped to an issuer against a proposed TRANSFER event *before* the
event reaches the append-only log. The engine never moves shares: it
either allows the write, hard-blocks it (BLOCK -> 409), or parks it in a
named-human review queue (REVIEW -> 409 + PENDING evaluation).

Principles carried over from Phases A-C:

- A named human resolves every REVIEW outcome (``reviewer`` is required
  and recorded -- same audit rule as capital-call review).
- ``ALLOWED`` and ``BLOCKED`` decisions are immutable audit rows too, so
  "why was this transfer permitted/forbidden" always has an answer.
- Every gate outcome appends exactly one ``transfer_evaluation`` ledger
  entry (PENDING creation does not -- the resolution does).
- Fail closed: any triggering BLOCK rule blocks, even if another rule
  would allow; ambiguous/unparseable condition values block.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import (
    CapTableEventType,
    LedgerEntryType,
    TransferEvaluationOutcome,
    TransferGate,
    TransferRuleType,
)
from app.models.orm import (
    LedgerEntry,
    Security,
    TransferEvaluation,
    TransferRule,
    _utcnow,
)


class TransferRuleError(ValueError):
    """Malformed rule input (maps to HTTP 400 at the API layer)."""


# The condition keys the engine actually reads. Every documented key is
# OPTIONAL: a rofr rule needs no window_days (it applies to every transfer
# from a non-exempt holder), board_approval needs no min_quantity (it
# applies to every transfer), bylaw_lockup needs no until_date (it applies
# indefinitely). When a key IS present it must type-check -- garbage is
# stopped at the door instead of failing closed at evaluation time.
# Everything else in the condition bag rides along verbatim into the audit
# record.
_OPTIONAL_CONDITION_KEYS: dict[
    TransferRuleType, tuple[tuple[str, type | tuple[type, ...]], ...]
] = {
    TransferRuleType.BYLAW_LOCKUP: (("until_date", str),),
}

# Shared numeric keys: must be a positive number when present, whatever the
# rule type (window_days also arrives as a top-level rule field, so it is
# validated globally rather than per rule_type).
_SHARED_POSITIVE_KEYS: tuple[str, ...] = ("window_days", "min_quantity")


def validate_rule_condition(
    rule_type: TransferRuleType | str, condition: dict[str, Any] | None
) -> dict[str, Any]:
    """Validate a rule's condition bag for its rule_type; 400-worthy
    problems raise :class:`TransferRuleError`. All documented keys are
    optional; unknown keys are preserved (forward compatibility -- new rule
    types must not need a migration)."""
    if condition is None:
        condition = {}
    if not isinstance(condition, dict):
        raise TransferRuleError("condition must be a JSON object")
    try:
        rt = TransferRuleType(rule_type)
    except ValueError as exc:
        raise TransferRuleError(f"unknown rule_type {rule_type!r}") from exc

    for key, expected in _OPTIONAL_CONDITION_KEYS.get(rt, ()):
        if key not in condition:
            continue
        value = condition[key]
        if not isinstance(value, expected) or isinstance(value, bool):
            raise TransferRuleError(
                f"condition key {key!r} must be of type "
                f"{getattr(expected, '__name__', expected)}"
            )

    for key in _SHARED_POSITIVE_KEYS:
        if key not in condition:
            continue
        value = condition[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TransferRuleError(f"condition key {key!r} must be a number")
        if value <= 0:
            raise TransferRuleError(f"condition key {key!r} must be positive")

    if rt is TransferRuleType.BYLAW_LOCKUP and "until_date" in condition:
        try:
            datetime.fromisoformat(
                str(condition["until_date"]).replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise TransferRuleError(
                "until_date must be an ISO-8601 datetime"
            ) from exc

    for list_key in ("exempt_holder_ids", "holder_ids"):
        if list_key in condition and not isinstance(condition[list_key], list):
            raise TransferRuleError(f"condition key {list_key!r} must be a list")

    return condition


def _iso(value: Any) -> datetime:
    """Parse an ISO-8601 datetime; naive values are treated as UTC."""
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _rule_triggered(rule: TransferRule, proposed: dict[str, Any]) -> bool:
    """Does this rule's condition fire on the proposed transfer? Unknown
    rule types never fire (fail open at the *rule* level, fail closed at
    the *decision* level -- an untriggered rule cannot block anyone)."""
    condition = rule.condition or {}
    try:
        if rule.rule_type is TransferRuleType.ROFR:
            exempt = set(condition.get("exempt_holder_ids") or [])
            return proposed["from_holder_id"] not in exempt
        if rule.rule_type is TransferRuleType.BOARD_APPROVAL:
            min_quantity = condition.get("min_quantity")
            if not isinstance(min_quantity, (int, float)) or isinstance(
                min_quantity, bool
            ):
                return False
            return proposed["quantity"] >= min_quantity
        if rule.rule_type is TransferRuleType.BYLAW_LOCKUP:
            if proposed["from_holder_id"] not in set(
                condition.get("holder_ids") or []
            ):
                return False
            until = _iso(condition["until_date"])
            return _iso(proposed["effective_date"]) < until
    except (KeyError, ValueError, TypeError):
        # Unparseable condition: fail closed -- treat as triggered so a
        # broken rule cannot silently open the gate.
        return True
    return False

def evaluate_transfer_rules(
    session: Session,
    security: Security,
    proposed: dict[str, Any],
) -> TransferEvaluation:
    """Run every active rule scoped to the security's issuer against one
    proposed TRANSFER, persist the immutable evaluation row, and append
    the outcome's single ledger entry (only for ALLOWED / BLOCKED -- a
    PENDING row's entry is written when a human resolves it).

    Returns the committed :class:`TransferEvaluation`. The caller routes
    on ``outcome``:

    - ``ALLOWED``  -> write the transfer event as usual
    - ``BLOCKED``  -> 409, nothing else written
    - ``PENDING``  -> 409 with ``evaluation_id``; goes to the review queue
    """
    rules = (
        session.execute(
            select(TransferRule)
            .where(TransferRule.issuer_name == security.issuer_name)
            .where(TransferRule.active.is_(True))
            .order_by(TransferRule.created_at, TransferRule.id)
        )
        .scalars()
        .all()
    )

    rules_evaluated: list[dict[str, Any]] = []
    blocking_rule: TransferRule | None = None
    needs_review = False

    for rule in rules:
        if not _rule_triggered(rule, proposed):
            continue
        rules_evaluated.append(
            {
                "rule_id": rule.id,
                "rule_type": rule.rule_type.value,
                "gate": rule.gate.value,
                "approver": rule.approver,
            }
        )
        if rule.gate is TransferGate.BLOCK:
            # Fail closed: a single BLOCK gate blocks the transfer even
            # if other rules would only demand review.
            blocking_rule = rule
            break
        needs_review = True

    if blocking_rule is not None:
        outcome = TransferEvaluationOutcome.BLOCKED
    elif needs_review:
        outcome = TransferEvaluationOutcome.PENDING
    else:
        outcome = TransferEvaluationOutcome.ALLOWED

    evaluation = TransferEvaluation(
        id=str(uuid4()),
        security_id=proposed["security_id"],
        from_holder_id=proposed["from_holder_id"],
        holder_id=proposed["holder_id"],
        quantity=proposed["quantity"],
        price_per_share=proposed.get("price_per_share"),
        effective_date=_iso(proposed["effective_date"]),
        rules_evaluated=rules_evaluated,
        outcome=outcome,
        blocking_rule_id=blocking_rule.id if blocking_rule else None,
    )
    session.add(evaluation)

    if outcome is not TransferEvaluationOutcome.PENDING:
        # Exactly one ledger entry per final gate outcome. A PENDING row
        # gets its entry when the named human approves or rejects it.
        session.add(
            LedgerEntry(
                id=str(uuid4()),
                entry_type=LedgerEntryType.TRANSFER_EVALUATION,
                payload={
                    "event": f"transfer_{outcome.value}",
                    "transfer_evaluation_id": evaluation.id,
                    "security_id": evaluation.security_id,
                    "from_holder_id": evaluation.from_holder_id,
                    "to_holder_id": evaluation.holder_id,
                    "quantity": evaluation.quantity,
                    "rules_evaluated": rules_evaluated,
                    "blocking_rule_id": evaluation.blocking_rule_id,
                },
            )
        )

    session.commit()
    session.refresh(evaluation)
    return evaluation
