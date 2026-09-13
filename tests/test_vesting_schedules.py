"""Tests for Vesting Schedules: grant-aware cap table computation,
point-in-time vesting, multi-grant FIFO consumption, leaver forfeiture,
and board-approved repurchase guards.
"""
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.captable import CapTableError, compute_cap_table, _add_months, completed_anniversary_months
from app.models.enums import CapTableEventType, InvestorType, SecurityType
from app.models.orm import CapTableEvent, Investor, Security


def _dt(days_from_now: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=days_from_now)


def _make_investor(session, name: str, investor_type: str = "individual") -> Investor:
    inv = Investor(
        id=f"inv-{name}", name=name, investor_type=InvestorType(investor_type)
    )
    session.add(inv)
    session.flush()
    return inv


def _make_security(session, issuer: str, name: str, sec_type: SecurityType, authorized: float) -> Security:
    sec = Security(
        id=f"sec-{issuer}-{name}".replace(" ", "-"),
        issuer_name=issuer, name=name, security_type=sec_type, authorized_shares=authorized,
    )
    session.add(sec)
    session.flush()
    return sec


def _grant(
    session,
    security: Security,
    holder: Investor,
    quantity: float,
    effective_date: datetime,
    vesting_start_date: date | None = None,
    vesting_period_months: int | None = None,
    cliff_months: int | None = None,
    acceleration_clause: str | None = None,
) -> CapTableEvent:
    event = CapTableEvent(
        id=f"grant-{security.id}-{holder.id}-{quantity}-{effective_date.timestamp()}",
        security_id=security.id,
        event_type=CapTableEventType.ISSUANCE,
        holder_id=holder.id,
        quantity=quantity,
        effective_date=effective_date,
        vesting_start_date=vesting_start_date,
        vesting_period_months=vesting_period_months,
        cliff_months=cliff_months,
        acceleration_clause=acceleration_clause,
    )
    session.add(event)
    session.flush()
    return event


# --------------------------------------------------------------------------- #
# Test 1: Standard 4-Year / 1-Year Cliff Milestones
# --------------------------------------------------------------------------- #


def test_standard_4_year_1_year_cliff_milestones(session):
    holder = _make_investor(session, "alice")
    options = _make_security(session, "Flowgate Inc", "Options", SecurityType.OPTION, 100_000)

    start = date(2024, 1, 1)
    eff = datetime(2024, 1, 1, tzinfo=timezone.utc)
    _grant(
        session,
        options,
        holder,
        quantity=48_000,
        effective_date=eff,
        vesting_start_date=start,
        vesting_period_months=48,
        cliff_months=12,
    )

    # 1. Month 6 (Pre-cliff) -> 0% vested
    as_of_m6 = datetime(2024, 7, 1, tzinfo=timezone.utc)
    snap_m6 = compute_cap_table(session, "Flowgate Inc", as_of=as_of_m6)
    pos_m6 = snap_m6.positions[0]
    assert pos_m6.shares == 48_000
    assert pos_m6.vested_shares == 0.0
    assert pos_m6.unvested_shares == 48_000.0
    assert snap_m6.total_vested_shares == 0.0
    assert snap_m6.total_unvested_shares == 48_000.0

    # 2. Month 12 (Cliff reached) -> exactly 25% (12,000 shares)
    as_of_m12 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    snap_m12 = compute_cap_table(session, "Flowgate Inc", as_of=as_of_m12)
    pos_m12 = snap_m12.positions[0]
    assert pos_m12.vested_shares == 12_000.0
    assert pos_m12.unvested_shares == 36_000.0

    # 3. Month 24 (Mid-schedule) -> exactly 50% (24,000 shares)
    as_of_m24 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    snap_m24 = compute_cap_table(session, "Flowgate Inc", as_of=as_of_m24)
    pos_m24 = snap_m24.positions[0]
    assert pos_m24.vested_shares == 24_000.0
    assert pos_m24.unvested_shares == 24_000.0

    # 4. Month 48 (Fully vested) -> 100% (48,000 shares)
    as_of_m48 = datetime(2028, 1, 1, tzinfo=timezone.utc)
    snap_m48 = compute_cap_table(session, "Flowgate Inc", as_of=as_of_m48)
    pos_m48 = snap_m48.positions[0]
    assert pos_m48.vested_shares == 48_000.0
    assert pos_m48.unvested_shares == 0.0
    assert snap_m48.grants[0].is_fully_vested is True


# --------------------------------------------------------------------------- #
# Test 2: Month-End & Leap-Year Arithmetic
# --------------------------------------------------------------------------- #


def test_month_end_and_leap_year_arithmetic():
    # Leap year 2024: Jan 31 -> Month 1 anniversary is Feb 29
    start_leap = date(2024, 1, 31)
    assert _add_months(start_leap, 1) == date(2024, 2, 29)
    assert completed_anniversary_months(start_leap, date(2024, 2, 28)) == 0
    assert completed_anniversary_months(start_leap, date(2024, 2, 29)) == 1

    # Non-leap year 2025: Jan 31 -> Month 1 anniversary is Feb 28
    start_non_leap = date(2025, 1, 31)
    assert _add_months(start_non_leap, 1) == date(2025, 2, 28)
    assert completed_anniversary_months(start_non_leap, date(2025, 2, 27)) == 0
    assert completed_anniversary_months(start_non_leap, date(2025, 2, 28)) == 1
    assert completed_anniversary_months(start_non_leap, date(2025, 3, 30)) == 1
    assert completed_anniversary_months(start_non_leap, date(2025, 3, 31)) == 2


# --------------------------------------------------------------------------- #
# Test 3: Explicit Multi-Grant FIFO Consumption
# --------------------------------------------------------------------------- #


def test_multi_grant_fifo_consumption(session):
    holder = _make_investor(session, "bob")
    buyer = _make_investor(session, "buyer")
    common = _make_security(session, "Acme Corp", "Common", SecurityType.COMMON, 500_000)

    # Grant 1: 50,000 shares on 2024-01-01 (100% vested immediately)
    g1 = _grant(
        session,
        common,
        holder,
        quantity=50_000,
        effective_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    # Grant 2: 20,000 shares on 2025-01-01 (100% vested immediately)
    g2 = _grant(
        session,
        common,
        holder,
        quantity=20_000,
        effective_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    # Transfer 60,000 shares on 2026-06-01
    transfer_evt = CapTableEvent(
        id="xfer-1",
        security_id=common.id,
        event_type=CapTableEventType.TRANSFER,
        from_holder_id=holder.id,
        holder_id=buyer.id,
        quantity=60_000,
        effective_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    session.add(transfer_evt)
    session.flush()

    snap = compute_cap_table(session, "Acme Corp", as_of=datetime(2026, 7, 1, tzinfo=timezone.utc))
    pos_bob = next(p for p in snap.positions if p.holder_id == holder.id)
    pos_buyer = next(p for p in snap.positions if p.holder_id == buyer.id)

    # Bob had 70,000, transferred 60,000 -> 10,000 remaining
    assert pos_bob.shares == 10_000
    assert pos_buyer.shares == 60_000


# --------------------------------------------------------------------------- #
# Test 4: Post-Transfer Vesting Continuation on Original Basis
# --------------------------------------------------------------------------- #


def test_post_transfer_vesting_continuation_on_original_basis(session):
    founder = _make_investor(session, "carol")
    buyer = _make_investor(session, "angel")
    sec = _make_security(session, "Beta Labs", "Common", SecurityType.COMMON, 100_000)

    # 50k grant over 48 months starting 2024-01-01
    _grant(
        session,
        sec,
        founder,
        quantity=50_000,
        effective_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        vesting_start_date=date(2024, 1, 1),
        vesting_period_months=48,
        cliff_months=12,
    )

    # At Month 24 (2026-01-01), 25,000 have vested. Transfer 10,000 vested shares.
    transfer = CapTableEvent(
        id="xfer-vested-1",
        security_id=sec.id,
        event_type=CapTableEventType.TRANSFER,
        from_holder_id=founder.id,
        holder_id=buyer.id,
        quantity=10_000,
        effective_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    session.add(transfer)
    session.flush()

    # Query at Month 36 (2027-01-01):
    # Original basis 50k: cumulative vested at M36 = 50k * 36/48 = 37,500
    # Net remaining held by Carol: 37,500 - 10,000 = 27,500 vested, and 50,000 - 37,500 = 12,500 unvested.
    # Total held: 40,000
    snap_m36 = compute_cap_table(session, "Beta Labs", as_of=datetime(2027, 1, 1, tzinfo=timezone.utc))
    pos_carol = next(p for p in snap_m36.positions if p.holder_id == founder.id)
    pos_buyer = next(p for p in snap_m36.positions if p.holder_id == buyer.id)

    assert pos_carol.shares == 40_000.0
    assert pos_carol.vested_shares == 27_500.0
    assert pos_carol.unvested_shares == 12_500.0
    assert pos_buyer.shares == 10_000.0
    assert pos_buyer.vested_shares == 10_000.0


# --------------------------------------------------------------------------- #
# Test 5: Post-Repurchase Vesting on Reduced Basis
# --------------------------------------------------------------------------- #


def test_post_repurchase_vesting_on_reduced_basis(session):
    founder = _make_investor(session, "dan")
    sec = _make_security(session, "Gamma Inc", "Common", SecurityType.COMMON, 100_000)

    # 50k grant over 48 months starting 2024-01-01
    _grant(
        session,
        sec,
        founder,
        quantity=50_000,
        effective_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        vesting_start_date=date(2024, 1, 1),
        vesting_period_months=48,
        cliff_months=12,
    )

    # At Month 24 (2026-01-01): 25k vested, 25k unvested.
    # Board-approved repurchase of 10k vested shares -> grant basis re-baselines to 40k.
    repurchase = CapTableEvent(
        id="repurchase-1",
        security_id=sec.id,
        event_type=CapTableEventType.CANCELLATION,
        from_holder_id=founder.id,
        quantity=10_000,
        effective_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        is_repurchase=True,
        repurchase_approver="Board Resolution #2026-04",
    )
    session.add(repurchase)
    session.flush()

    # Query at Month 36 (2027-01-01):
    # Under reduced basis 40k: cumulative vested at M36 = 40k * 36/48 = 30k vested held, 10k unvested held.
    # Total held = 40k.
    snap_m36 = compute_cap_table(session, "Gamma Inc", as_of=datetime(2027, 1, 1, tzinfo=timezone.utc))
    pos_dan = next(p for p in snap_m36.positions if p.holder_id == founder.id)

    assert pos_dan.shares == 40_000.0
    assert pos_dan.vested_shares == 30_000.0
    assert pos_dan.unvested_shares == 10_000.0


# --------------------------------------------------------------------------- #
# Test 6: Unvested Transfer Prohibition
# --------------------------------------------------------------------------- #


def test_unvested_transfer_prohibition(session):
    founder = _make_investor(session, "eva")
    buyer = _make_investor(session, "buyer-eva")
    sec = _make_security(session, "Delta Inc", "Options", SecurityType.OPTION, 100_000)

    # 48k grant starting 2024-01-01 with 12-month cliff
    _grant(
        session,
        sec,
        founder,
        quantity=48_000,
        effective_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        vesting_start_date=date(2024, 1, 1),
        vesting_period_months=48,
        cliff_months=12,
    )

    # Attempt to transfer 1,000 shares at Month 6 (0 vested)
    bad_xfer = CapTableEvent(
        id="bad-xfer",
        security_id=sec.id,
        event_type=CapTableEventType.TRANSFER,
        from_holder_id=founder.id,
        holder_id=buyer.id,
        quantity=1_000,
        effective_date=datetime(2024, 7, 1, tzinfo=timezone.utc),
    )
    session.add(bad_xfer)
    session.flush()

    with pytest.raises(CapTableError) as exc_info:
        compute_cap_table(session, "Delta Inc", as_of=datetime(2024, 7, 2, tzinfo=timezone.utc))
    assert "only has 0.0 vested shares" in str(exc_info.value)


# --------------------------------------------------------------------------- #
# Test 7: Leaver Forfeiture vs. Board Repurchase (Reading B)
# --------------------------------------------------------------------------- #


def test_leaver_forfeiture_vs_repurchase(session):
    leaver = _make_investor(session, "frank")
    sec = _make_security(session, "Epsilon Co", "Options", SecurityType.OPTION, 100_000)

    # At 2024-01-01: 50k grant over 48 months with 12m cliff
    _grant(
        session,
        sec,
        leaver,
        quantity=50_000,
        effective_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        vesting_start_date=date(2024, 1, 1),
        vesting_period_months=48,
        cliff_months=12,
    )

    # At Month 24: Frank has 25k vested, 25k unvested.
    # Frank leaves. Cancel 25k unvested options (is_repurchase=False)
    forfeiture = CapTableEvent(
        id="forfeiture-1",
        security_id=sec.id,
        event_type=CapTableEventType.CANCELLATION,
        from_holder_id=leaver.id,
        quantity=25_000,
        effective_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        is_repurchase=False,
    )
    session.add(forfeiture)
    session.flush()

    # Frank keeps his 25k vested options, 0 unvested
    snap = compute_cap_table(session, "Epsilon Co", as_of=datetime(2026, 1, 2, tzinfo=timezone.utc))
    pos = snap.positions[0]
    assert pos.shares == 25_000.0
    assert pos.vested_shares == 25_000.0
    assert pos.unvested_shares == 0.0

    # If company tries to cancel Frank's remaining 25k vested options without is_repurchase=True -> fails!
    bad_cancel = CapTableEvent(
        id="bad-cancel-vested",
        security_id=sec.id,
        event_type=CapTableEventType.CANCELLATION,
        from_holder_id=leaver.id,
        quantity=10_000,
        effective_date=datetime(2026, 1, 3, tzinfo=timezone.utc),
        is_repurchase=False,
    )
    session.add(bad_cancel)
    session.flush()
    with pytest.raises(CapTableError) as exc_info:
        compute_cap_table(session, "Epsilon Co", as_of=datetime(2026, 1, 4, tzinfo=timezone.utc))
    assert "Cancelling vested shares requires is_repurchase=True" in str(exc_info.value)


# --------------------------------------------------------------------------- #
# Test 8: Future-Dated and Backdated Grants
# --------------------------------------------------------------------------- #


def test_future_and_backdated_grants(session):
    holder = _make_investor(session, "george")
    sec = _make_security(session, "Zeta Co", "Common", SecurityType.COMMON, 100_000)

    # Future-dated: grant signed now, vesting starts in 2028
    _grant(
        session,
        sec,
        holder,
        quantity=10_000,
        effective_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        vesting_start_date=date(2028, 1, 1),
        vesting_period_months=48,
        cliff_months=12,
    )

    snap = compute_cap_table(session, "Zeta Co", as_of=datetime(2026, 6, 1, tzinfo=timezone.utc))
    pos = snap.positions[0]
    assert pos.shares == 10_000.0
    assert pos.vested_shares == 0.0
    assert pos.unvested_shares == 10_000.0


# --------------------------------------------------------------------------- #
# Test 9: Fractional / Non-Round Share Allocations
# --------------------------------------------------------------------------- #


def test_fractional_non_round_share_allocations(session):
    holder = _make_investor(session, "helen")
    sec = _make_security(session, "Eta Co", "Options", SecurityType.OPTION, 10_000)

    # 999 shares over 48 months with 12 month cliff
    _grant(
        session,
        sec,
        holder,
        quantity=999,
        effective_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        vesting_start_date=date(2024, 1, 1),
        vesting_period_months=48,
        cliff_months=12,
    )

    # At Month 12: 999 * (12/48) = 249.75 shares
    snap_m12 = compute_cap_table(session, "Eta Co", as_of=datetime(2025, 1, 1, tzinfo=timezone.utc))
    pos = snap_m12.positions[0]
    assert pos.vested_shares == 249.75
    assert pos.unvested_shares == 749.25


# --------------------------------------------------------------------------- #
# Test 10: API Endpoints & Validation Guards
# --------------------------------------------------------------------------- #


def test_api_vesting_endpoints_and_guards(client: TestClient):
    # Setup security and investor via API
    sec_resp = client.post(
        "/securities",
        json={
            "issuer_name": "API Corp",
            "name": "Option Pool 2026",
            "security_type": "option",
            "authorized_shares": 100_000,
        },
    )
    assert sec_resp.status_code == 201
    sec_id = sec_resp.json()["id"]

    inv_resp = client.post(
        "/investors",
        json={"name": "Ian Developer", "investor_type": "individual"},
    )
    assert inv_resp.status_code == 201
    inv_id = inv_resp.json()["id"]

    # 1. Validation guard: cliff > period -> 422/400 validation error
    bad_cliff = client.post(
        "/cap-table-events",
        json={
            "security_id": sec_id,
            "event_type": "issuance",
            "holder_id": inv_id,
            "quantity": 20_000,
            "effective_date": "2024-01-01T00:00:00Z",
            "vesting_start_date": "2024-01-01",
            "vesting_period_months": 24,
            "cliff_months": 36,  # > period!
        },
    )
    assert bad_cliff.status_code in (400, 422)

    # 2. Validation guard: vesting fields on non-issuance -> 400
    bad_type = client.post(
        "/cap-table-events",
        json={
            "security_id": sec_id,
            "event_type": "cancellation",
            "from_holder_id": inv_id,
            "quantity": 1_000,
            "effective_date": "2024-01-01T00:00:00Z",
            "vesting_period_months": 48,
        },
    )
    assert bad_type.status_code == 400

    # 3. Create valid issuance with vesting schedule
    valid_grant = client.post(
        "/cap-table-events",
        json={
            "security_id": sec_id,
            "event_type": "issuance",
            "holder_id": inv_id,
            "quantity": 48_000,
            "effective_date": "2024-01-01T00:00:00Z",
            "vesting_start_date": "2024-01-01",
            "vesting_period_months": 48,
            "cliff_months": 12,
            "acceleration_clause": "double_trigger",
        },
    )
    assert valid_grant.status_code == 201
    grant_json = valid_grant.json()
    assert grant_json["vesting_period_months"] == 48
    assert grant_json["acceleration_clause"] == "double_trigger"

    # 4. GET /cap-table/{issuer} reflects vested and unvested positions and grants
    cap_resp = client.get(
        "/cap-table/API Corp?as_of=2025-01-01T00:00:00Z"
    )
    assert cap_resp.status_code == 200
    cap_json = cap_resp.json()
    assert cap_json["total_fully_diluted_shares"] == 48_000
    assert cap_json["total_vested_shares"] == 12_000
    assert cap_json["total_unvested_shares"] == 36_000
    assert len(cap_json["grants"]) == 1
    assert cap_json["grants"][0]["vested_shares"] == 12_000
    assert cap_json["grants"][0]["acceleration_clause"] == "double_trigger"


# --------------------------------------------------------------------------- #
# Test 11: Live-first frontend payload contract (the wiring this phase fixed)
# --------------------------------------------------------------------------- #


def test_react_live_first_vesting_payload_contract(client: TestClient):
    # Mirrors src/App.tsx handleRecordEvent -> createCapTableEvent exactly:
    # every vesting/repurchase field is forwarded (null when absent) and
    # transfers map transferor -> from_holder_id, recipient -> holder_id.
    sec = client.post(
        "/securities", json={
            "issuer_name": "React Corpa", "name": "ESOP", "security_type": "option", "authorized_shares": 100_000,
        },
    )
    assert sec.status_code == 201
    sec_id = sec.json()["id"]

    inv = client.post("/investors", json={"name": "Dev One", "investor_type": "individual"})
    assert inv.status_code == 201
    inv_id = inv.json()["id"]

    # 1. Issuance WITH vesting schedule (the fields CapTableView.tsx collects).
    grant = client.post(
        "/cap-table-events",
        json={
            "security_id": sec_id,
            "event_type": "issuance",
            "holder_id": inv_id,
            "quantity": 48_000,
            "price_per_share": 1.0,
            "effective_date": "2024-01-01T00:00:00Z",
            "vesting_start_date": "2024-01-01",
            "vesting_period_months": 48,
            "cliff_months": 12,
            "acceleration_clause": "single_trigger",
            "is_repurchase": False,
            "repurchase_approver": None,
        },
    )
    assert grant.status_code == 201, grant.text
    body = grant.json()
    assert body["vesting_start_date"] == "2024-01-01"
    assert body["vesting_period_months"] == 48
    assert body["cliff_months"] == 12
    assert body["acceleration_clause"] == "single_trigger"

    # 2. Cap table grants panel data comes back (the UI hydrates from it).
    cap = client.get("/cap-table/React%20Corpa?as_of=2025-01-01")
    assert cap.status_code == 200
    cap_json = cap.json()
    assert cap_json["total_vested_shares"] == 12_000
    assert len(cap_json["grants"]) == 1
    assert cap_json["grants"][0]["acceleration_clause"] == "single_trigger"
    grant_id = cap_json["grants"][0]["event_id"]
    assert grant_id
    # 3. A transfer now carries transferor -> from_holder_id (was broken live).
    buyer = client.post("/investors", json={"name": "Buyer Two", "investor_type": "institution"})
    buyer_id = buyer.json()["id"]
    out = client.post("/cap-table-events",
        json={
            "security_id": sec_id,
            "event_type": "transfer",
            "from_holder_id": inv_id,
            "holder_id": buyer_id,
            "quantity": 6_000,
            "effective_date": "2025-01-01T00:00:00Z",
            "vesting_start_date": None,
            "vesting_period_months": None,
            "cliff_months": None,
            "acceleration_clause": None,
            "is_repurchase": False,
            "repurchase_approver": None,
        },
    )
    assert out.status_code == 201, out.text
    # Transferee now holds the vested shares that moved.
    after = client.get("/cap-table/React%20Corpa").json()
    buyer_pos = next((p for p in after["positions"] if p["holder_id"] == buyer_id), None)
    assert buyer_pos is not None and buyer_pos["shares"] == 6_000

