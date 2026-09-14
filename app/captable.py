"""Cap table computation: the current (or point-in-time) ownership picture
is always *derived* from the CapTableEvent log, never stored directly.

This is the actual mechanic that makes a cap table correct under dilution,
transfers, and cancellations, instead of a spreadsheet someone has to
remember to keep in sync. Every function here is pure -- given the same
events and the same as_of date, it always produces the same answer, which
is what makes "what did ownership look like on March 3rd" an answerable
question rather than a lost fact.
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import CapTableEventType
from app.models.orm import CapTableEvent, Security


# --------------------------------------------------------------------------- #
# Calendar Anniversary Arithmetic (No Timezone Drift)
# --------------------------------------------------------------------------- #


def _add_months(d: date, months: int) -> date:
    """Add `months` calendar months to date `d`, with month-end clipping."""
    new_year = d.year + (d.month - 1 + months) // 12
    new_month = (d.month - 1 + months) % 12 + 1
    max_day = calendar.monthrange(new_year, new_month)[1]
    new_day = min(d.day, max_day)
    return date(new_year, new_month, new_day)


def completed_anniversary_months(start_date: date, as_of_date: date) -> int:
    """Returns the integer count of completed calendar-month anniversaries between
    `start_date` and `as_of_date`. Returns 0 if as_of_date < start_date."""
    if as_of_date < start_date:
        return 0
    approx = (as_of_date.year - start_date.year) * 12 + (as_of_date.month - start_date.month)
    if _add_months(start_date, approx) <= as_of_date:
        return approx
    return max(0, approx - 1)


# --------------------------------------------------------------------------- #
# Snapshot Dataclasses
# --------------------------------------------------------------------------- #


@dataclass
class HolderPosition:
    holder_id: str
    security_id: str
    shares: float
    vested_shares: float = 0.0
    unvested_shares: float = 0.0


@dataclass
class GrantVestingSnapshot:
    event_id: str
    security_id: str
    holder_id: str
    original_shares: float
    total_shares: float
    vested_shares: float
    unvested_shares: float
    transferred_vested_shares: float
    repurchased_vested_shares: float
    vesting_start_date: date
    vesting_period_months: int
    cliff_months: int
    cliff_date: date | None
    fully_vested_date: date | None
    is_fully_vested: bool
    acceleration_clause: str | None


@dataclass
class CapTableSnapshot:
    as_of: datetime
    issuer_name: str
    positions: list[HolderPosition] = field(default_factory=list)
    shares_by_security: dict[str, float] = field(default_factory=dict)
    total_fully_diluted_shares: float = 0.0
    total_vested_shares: float = 0.0
    total_unvested_shares: float = 0.0
    grants: list[GrantVestingSnapshot] = field(default_factory=list)

    def ownership_by_holder(self) -> dict[str, float]:
        """Fully-diluted ownership percentage per holder, across all
        securities. 'Fully diluted' here means every outstanding share of
        every security counts in the denominator, including unexercised
        options and warrants -- the standard cap-table convention, and the
        reason a founder's percentage drops the moment an option pool is
        created, not only when options are actually exercised.
        """
        if self.total_fully_diluted_shares <= 0:
            return {}
        totals: dict[str, float] = defaultdict(float)
        for p in self.positions:
            totals[p.holder_id] += p.shares
        return {
            holder_id: round(shares / self.total_fully_diluted_shares * 100, 4)
            for holder_id, shares in totals.items()
        }


# --------------------------------------------------------------------------- #
# SAFE / Convertible Conversion Arithmetic
# --------------------------------------------------------------------------- #


@dataclass
class ConversionResult:
    """Result of converting a single convertible (SAFE) into a priced round."""
    convertible_id: str
    investor_name: str
    purchase_amount: float
    pricing_basis: str           # "cap" | "discount"
    conversion_price: float
    shares_issued: float
    cap_price: float | None
    discount_price: float | None


class ConversionError(ValueError):
    """Raised when conversion parameters are invalid or impossible."""


def compute_conversions(
    convertibles: list,
    round_price: float,
    pre_safe_shares: int,
    options_pool: int,
) -> list[ConversionResult]:
    """
    Compute conversion shares for a batch of post-money SAFEs against
    a priced round. Uses the YC post-money SAFE formula:

        owner_i = purchase_amount_i / valuation_cap_i
        sum_owner = Σ owner_j
        shares_i  = owner_i / (1 − sum_owner) × (pre_safe_shares + options_pool)

    For each convertible, compare the cap-derived price (purchase / shares)
    against the discount price (round_price × (1 − discount_rate)) and
    take the lower (which yields more shares for the investor).

    Args:
        convertibles: List of Convertible ORM objects (or dicts with the
            same fields). Only those with instrument_kind == "post_money_safe"
            are processed; pre-money SAFEs raise ConversionError.
        round_price: Price per share of the priced round (must be > 0).
        pre_safe_shares: Total shares outstanding before any SAFE conversion.
        options_pool: Unallocated option pool shares.

    Returns:
        List of ConversionResult, one per convertible.

    Raises:
        ConversionError: If round_price <= 0, any SAFE is pre-money,
            sum_owner >= 1.0, or any valuation_cap <= 0.
    """
    if round_price <= 0:
        raise ConversionError("round_price must be positive")

    # Validate and filter to post-money SAFEs
    post_money = []
    for c in convertibles:
        kind = getattr(c, "instrument_kind",
                       c.get("instrument_kind") if isinstance(c, dict) else None)
        if kind != "post_money_safe":
            cid = getattr(c, "id",
                          c.get("id") if isinstance(c, dict) else "unknown")
            raise ConversionError(
                f"Pre-money SAFE conversion is not yet supported. "
                f"Convertible {cid} has instrument_kind={kind!r}. "
                f"Use manual override."
            )
        cap = getattr(c, "valuation_cap",
                      c.get("valuation_cap") if isinstance(c, dict) else None)
        if cap is None or cap <= 0:
            cid = getattr(c, "id",
                          c.get("id") if isinstance(c, dict) else "unknown")
            raise ConversionError(
                f"Convertible {cid} has invalid valuation_cap={cap!r}"
            )
        post_money.append(c)

    # Compute owner_i = purchase_amount_i / valuation_cap_i
    owners = []
    for c in post_money:
        amount = getattr(c, "purchase_amount",
                         c.get("purchase_amount") if isinstance(c, dict) else None)
        cap = getattr(c, "valuation_cap",
                      c.get("valuation_cap") if isinstance(c, dict) else None)
        owners.append(amount / cap)

    sum_owner = sum(owners)
    if sum_owner >= 1.0:
        raise ConversionError(
            f"Total SAFE ownership fraction {sum_owner:.6f} >= 1.0 -- "
            "SAFEs would own 100%+ of the company (data error)"
        )

    denominator = 1.0 - sum_owner
    common_base = pre_safe_shares + options_pool

    results = []
    for c, owner in zip(post_money, owners):
        amount = getattr(c, "purchase_amount",
                         c.get("purchase_amount") if isinstance(c, dict) else None)
        disc = getattr(c, "discount_rate",
                       c.get("discount_rate") if isinstance(c, dict) else None)

        # Cap-derived shares and price
        cap_shares = (owner / denominator) * common_base
        cap_price = amount / cap_shares if cap_shares > 0 else float("inf")

        # Discount price
        if disc is not None and disc > 0:
            discount_price = round_price * (1.0 - disc)
        else:
            discount_price = float("inf")

        # Choose the lower price (more shares for investor)
        if cap_price <= discount_price:
            basis = "cap"
            conversion_price = cap_price
            shares = cap_shares
        else:
            basis = "discount"
            conversion_price = discount_price
            shares = amount / discount_price

        results.append(ConversionResult(
            convertible_id=getattr(c, "id",
                                   c.get("id", "") if isinstance(c, dict) else ""),
            investor_name=getattr(c, "investor_name",
                                 c.get("investor_name", "") if isinstance(c, dict) else ""),
            purchase_amount=amount,
            pricing_basis=basis,
            conversion_price=conversion_price,
            shares_issued=shares,
            cap_price=cap_price,
            discount_price=discount_price,
        ))

    return results


class CapTableError(ValueError):
    """Raised when the event log itself is inconsistent -- e.g. a transfer
    or cancellation that would take a holder's position negative, or an
    unvested transfer attempt. This is a data-integrity signal, not a business
    decision the caller should silently paper over."""


# --------------------------------------------------------------------------- #
# Internal Replay Grant State
# --------------------------------------------------------------------------- #


class _GrantState:
    def __init__(
        self,
        event_id: str,
        security_id: str,
        holder_id: str,
        quantity: float,
        effective_date: datetime,
        vesting_start_date: date,
        vesting_period_months: int | None = None,
        cliff_months: int | None = None,
        acceleration_clause: str | None = None,
    ):
        self.event_id = event_id
        self.security_id = security_id
        self.holder_id = holder_id
        self.effective_date = effective_date
        self.original_shares = float(quantity)
        self.basis_shares = float(quantity)
        self.vesting_start_date = vesting_start_date
        self.vesting_period_months = int(vesting_period_months or 0)
        self.cliff_months = int(cliff_months or 0)
        self.acceleration_clause = acceleration_clause

        self.transferred_vested_shares: float = 0.0
        self.repurchased_vested_shares: float = 0.0
        self.forfeited_unvested_shares: float = 0.0
        self.vesting_stopped_at_vested: float | None = None

    @classmethod
    def from_event(cls, event: CapTableEvent) -> _GrantState:
        if event.vesting_start_date is not None:
            v_start = event.vesting_start_date
        elif isinstance(event.effective_date, datetime):
            v_start = event.effective_date.date()
        else:
            v_start = event.effective_date

        return cls(
            event_id=event.id,
            security_id=event.security_id,
            holder_id=event.holder_id,
            quantity=event.quantity,
            effective_date=event.effective_date,
            vesting_start_date=v_start,
            vesting_period_months=event.vesting_period_months,
            cliff_months=event.cliff_months,
            acceleration_clause=event.acceleration_clause,
        )

    @property
    def has_vesting(self) -> bool:
        return self.vesting_period_months > 0

    def cumulative_vested_at(self, as_of_d: date) -> float:
        if not self.has_vesting:
            return self.basis_shares
        if self.vesting_stopped_at_vested is not None:
            return self.vesting_stopped_at_vested
        if as_of_d < self.vesting_start_date:
            return 0.0
        elapsed_m = completed_anniversary_months(self.vesting_start_date, as_of_d)
        if elapsed_m < self.cliff_months:
            return 0.0
        ratio = min(1.0, elapsed_m / self.vesting_period_months)
        return self.basis_shares * ratio

    def current_vested_at(self, as_of_d: date) -> float:
        cum = self.cumulative_vested_at(as_of_d)
        return max(0.0, cum - self.transferred_vested_shares)

    def current_unvested_at(self, as_of_d: date) -> float:
        if not self.has_vesting:
            return 0.0
        if self.vesting_stopped_at_vested is not None:
            return 0.0
        cum = self.cumulative_vested_at(as_of_d)
        unvested = self.basis_shares - cum - self.forfeited_unvested_shares
        return max(0.0, unvested)

    def total_held_at(self, as_of_d: date) -> float:
        return self.current_vested_at(as_of_d) + self.current_unvested_at(as_of_d)


# --------------------------------------------------------------------------- #
# Cap Table Replay Computation
# --------------------------------------------------------------------------- #


def compute_cap_table(
    session: Session, issuer_name: str, as_of: datetime | None = None
) -> CapTableSnapshot:
    as_of = as_of or datetime.now(timezone.utc)
    final_as_of_d = as_of.date() if isinstance(as_of, datetime) else as_of

    security_rows = session.execute(
        select(Security).where(Security.issuer_name == issuer_name)
    ).scalars().all()
    security_ids = {s.id for s in security_rows}
    if not security_ids:
        return CapTableSnapshot(as_of=as_of, issuer_name=issuer_name)

    events = session.execute(
        select(CapTableEvent)
        .where(
            CapTableEvent.security_id.in_(security_ids),
            CapTableEvent.effective_date <= as_of,
        )
        .order_by(CapTableEvent.effective_date, CapTableEvent.recorded_at)
    ).scalars().all()

    positions: dict[tuple[str, str], float] = defaultdict(float)
    grants_by_holder: dict[tuple[str, str], list[_GrantState]] = defaultdict(list)

    for event in events:
        event_d = event.effective_date.date() if isinstance(event.effective_date, datetime) else event.effective_date

        if event.event_type == CapTableEventType.ISSUANCE:
            if not event.holder_id:
                raise CapTableError(f"Issuance event {event.id} has no holder_id")
            key = (event.security_id, event.holder_id)
            positions[key] += event.quantity
            grant = _GrantState.from_event(event)
            grants_by_holder[key].append(grant)

        elif event.event_type == CapTableEventType.TRANSFER:
            if not event.from_holder_id or not event.holder_id:
                raise CapTableError(
                    f"Transfer event {event.id} needs both from_holder_id and holder_id"
                )
            key_from = (event.security_id, event.from_holder_id)
            if positions[key_from] < event.quantity:
                raise CapTableError(
                    f"Transfer event {event.id} moves {event.quantity} shares but "
                    f"holder {event.from_holder_id!r} only has {positions[key_from]}"
                )
            from_grants = grants_by_holder[key_from]
            available_vested = sum(g.current_vested_at(event_d) for g in from_grants)
            if available_vested < event.quantity:
                raise CapTableError(
                    f"Transfer event {event.id} moves {event.quantity} shares but "
                    f"holder {event.from_holder_id!r} only has {available_vested} vested shares"
                )
            # Consume from oldest vested grants via FIFO (original grant basis continues)
            rem = event.quantity
            for g in from_grants:
                v = g.current_vested_at(event_d)
                if v <= 0:
                    continue
                take = min(rem, v)
                g.transferred_vested_shares += take
                rem -= take
                if rem <= 0:
                    break

            positions[key_from] -= event.quantity
            key_to = (event.security_id, event.holder_id)
            positions[key_to] += event.quantity
            # Transferee receives fully-vested shares
            recipient_grant = _GrantState(
                event_id=f"{event.id}-rcpt",
                security_id=event.security_id,
                holder_id=event.holder_id,
                quantity=event.quantity,
                effective_date=event.effective_date,
                vesting_start_date=event_d,
                vesting_period_months=0,
                cliff_months=0,
            )
            grants_by_holder[key_to].append(recipient_grant)

        elif event.event_type == CapTableEventType.CANCELLATION:
            if not event.from_holder_id:
                raise CapTableError(f"Cancellation event {event.id} has no from_holder_id")
            key = (event.security_id, event.from_holder_id)
            if positions[key] < event.quantity:
                raise CapTableError(
                    f"Cancellation event {event.id} cancels {event.quantity} shares but "
                    f"holder {event.from_holder_id!r} only has {positions[key]}"
                )
            from_grants = grants_by_holder[key]

            if getattr(event, "is_repurchase", False):
                # Repurchase of vested shares (board approved)
                available_vested = sum(g.current_vested_at(event_d) for g in from_grants)
                if available_vested < event.quantity:
                    raise CapTableError(
                        f"Repurchase event {event.id} repurchases {event.quantity} shares but "
                        f"holder {event.from_holder_id!r} only has {available_vested} vested shares"
                    )
                # Consume from vested shares via FIFO on reduced basis
                rem = event.quantity
                for g in from_grants:
                    v = g.current_vested_at(event_d)
                    if v <= 0:
                        continue
                    take = min(rem, v)
                    g.repurchased_vested_shares += take
                    g.basis_shares -= take  # re-baselines grant to reduced basis
                    if g.vesting_stopped_at_vested is not None:
                        g.vesting_stopped_at_vested -= take
                    rem -= take
                    if rem <= 0:
                        break
            else:
                # Standard cancellation: leaver departure forfeiture of unvested options
                has_vesting = any(g.has_vesting for g in from_grants)
                if has_vesting:
                    available_unvested = sum(g.current_unvested_at(event_d) for g in from_grants)
                    if available_unvested < event.quantity:
                        raise CapTableError(
                            f"Cancellation event {event.id} cancels {event.quantity} shares but "
                            f"holder {event.from_holder_id!r} only has {available_unvested} unvested shares. "
                            "Cancelling vested shares requires is_repurchase=True and repurchase_approver."
                        )
                    rem = event.quantity
                    for g in from_grants:
                        u = g.current_unvested_at(event_d)
                        if u <= 0:
                            continue
                        take = min(rem, u)
                        g.forfeited_unvested_shares += take
                        g.vesting_stopped_at_vested = g.current_vested_at(event_d)
                        rem -= take
                        if rem <= 0:
                            break
                else:
                    # Legacy non-vesting grant (e.g. founder stock without vesting schedule)
                    rem = event.quantity
                    for g in from_grants:
                        held = g.total_held_at(event_d)
                        if held <= 0:
                            continue
                        take = min(rem, held)
                        g.basis_shares -= take
                        rem -= take
                        if rem <= 0:
                            break

            positions[key] -= event.quantity

        elif event.event_type in (CapTableEventType.EXERCISE, CapTableEventType.CONVERSION):
            if not event.holder_id or not event.target_security_id:
                raise CapTableError(
                    f"{event.event_type.value} event {event.id} needs holder_id and "
                    "target_security_id"
                )
            key_source = (event.security_id, event.holder_id)
            if positions[key_source] < event.quantity:
                raise CapTableError(
                    f"{event.event_type.value} event {event.id} moves {event.quantity} "
                    f"shares but holder {event.holder_id!r} only has {positions[key_source]}"
                )
            from_grants = grants_by_holder[key_source]
            available_vested = sum(g.current_vested_at(event_d) for g in from_grants)
            if available_vested < event.quantity:
                raise CapTableError(
                    f"{event.event_type.value} event {event.id} moves {event.quantity} "
                    f"shares but holder {event.holder_id!r} only has {available_vested} vested shares"
                )
            rem = event.quantity
            for g in from_grants:
                v = g.current_vested_at(event_d)
                if v <= 0:
                    continue
                take = min(rem, v)
                g.transferred_vested_shares += take
                rem -= take
                if rem <= 0:
                    break

            positions[key_source] -= event.quantity
            key_target = (event.target_security_id, event.holder_id)
            positions[key_target] += event.quantity
            target_grant = _GrantState(
                event_id=f"{event.id}-target",
                security_id=event.target_security_id,
                holder_id=event.holder_id,
                quantity=event.quantity,
                effective_date=event.effective_date,
                vesting_start_date=event_d,
                vesting_period_months=0,
                cliff_months=0,
            )
            grants_by_holder[key_target].append(target_grant)

        else:  # pragma: no cover
            raise CapTableError(f"Unknown event type {event.event_type!r}")

    result_positions = []
    shares_by_security: dict[str, float] = defaultdict(float)

    for (s, h), qty in positions.items():
        if qty > 0:
            grants = grants_by_holder[(s, h)]
            v_shares = sum(g.current_vested_at(final_as_of_d) for g in grants)
            u_shares = sum(g.current_unvested_at(final_as_of_d) for g in grants)
            result_positions.append(
                HolderPosition(
                    holder_id=h,
                    security_id=s,
                    shares=qty,
                    vested_shares=round(v_shares, 4),
                    unvested_shares=round(u_shares, 4),
                )
            )
            shares_by_security[s] += qty

    # Compile grant snapshots for grants with vesting schedules
    active_grants: list[GrantVestingSnapshot] = []
    for (s, h), grants in grants_by_holder.items():
        for g in grants:
            if g.has_vesting and g.total_held_at(final_as_of_d) > 0:
                cliff_d = _add_months(g.vesting_start_date, g.cliff_months) if g.cliff_months > 0 else g.vesting_start_date
                fully_d = _add_months(g.vesting_start_date, g.vesting_period_months)
                vested = g.current_vested_at(final_as_of_d)
                unvested = g.current_unvested_at(final_as_of_d)
                active_grants.append(
                    GrantVestingSnapshot(
                        event_id=g.event_id,
                        security_id=g.security_id,
                        holder_id=g.holder_id,
                        original_shares=g.original_shares,
                        total_shares=round(vested + unvested, 4),
                        vested_shares=round(vested, 4),
                        unvested_shares=round(unvested, 4),
                        transferred_vested_shares=round(g.transferred_vested_shares, 4),
                        repurchased_vested_shares=round(g.repurchased_vested_shares, 4),
                        vesting_start_date=g.vesting_start_date,
                        vesting_period_months=g.vesting_period_months,
                        cliff_months=g.cliff_months,
                        cliff_date=cliff_d,
                        fully_vested_date=fully_d,
                        is_fully_vested=(unvested <= 0.0),
                        acceleration_clause=g.acceleration_clause,
                    )
                )

    total_diluted = sum(shares_by_security.values())
    total_vested = sum(p.vested_shares for p in result_positions)
    total_unvested = sum(p.unvested_shares for p in result_positions)

    return CapTableSnapshot(
        as_of=as_of,
        issuer_name=issuer_name,
        positions=result_positions,
        shares_by_security=dict(shares_by_security),
        total_fully_diluted_shares=round(total_diluted, 4),
        total_vested_shares=round(total_vested, 4),
        total_unvested_shares=round(total_unvested, 4),
        grants=active_grants,
    )