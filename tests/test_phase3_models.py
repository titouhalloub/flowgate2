"""ORM round-trip tests for Phase 3.1 — Convertible and PricedRound models."""
import pytest
from datetime import date, datetime, timezone
from uuid import uuid4

from app.models.orm import Convertible, PricedRound, ConvertibleStatus


def test_convertible_roundtrip(session):
    """Create a Convertible, commit, and read it back with all fields intact."""
    c = Convertible(
        id=str(uuid4()),
        issuer_name="Acme Corp",
        investor_name="VC Fund I",
        document_id=None,
        purchase_amount=1_000_000.0,
        currency="USD",
        instrument_kind="post_money_safe",
        valuation_cap=20_000_000.0,
        discount_rate=0.20,
        pro_rata_rights=True,
        mfn_clause=False,
        conversion_trigger="Equity financing",
        issued_date=date(2026, 1, 15),
        status=ConvertibleStatus.OUTSTANDING,
        converted_at=None,
        conversion_event_id=None,
    )
    session.add(c)
    session.commit()
    session.refresh(c)

    assert c.id is not None
    assert c.issuer_name == "Acme Corp"
    assert c.investor_name == "VC Fund I"
    assert c.purchase_amount == 1_000_000.0
    assert c.instrument_kind == "post_money_safe"
    assert c.valuation_cap == 20_000_000.0
    assert c.discount_rate == 0.20
    assert c.pro_rata_rights is True
    assert c.mfn_clause is False
    assert c.issued_date == date(2026, 1, 15)
    assert c.status == ConvertibleStatus.OUTSTANDING
    assert c.converted_at is None
    assert c.conversion_event_id is None
    assert c.created_at is not None
    assert c.updated_at is not None


def test_priced_round_roundtrip(session):
    """Create a PricedRound, commit, and read it back with all fields intact."""
    r = PricedRound(
        id=str(uuid4()),
        issuer_name="Acme Corp",
        round_name="Series A",
        price_per_share=1.00,
        round_shares=5_000_000,
        post_money_shares=45_000_000,
        effective_date=date(2026, 6, 1),
        reviewer="Sarah Jenkins (Legal VP)",
        notes="Lead investor: Sequoia",
        client_request_id=str(uuid4()),
    )
    session.add(r)
    session.commit()
    session.refresh(r)

    assert r.id is not None
    assert r.issuer_name == "Acme Corp"
    assert r.round_name == "Series A"
    assert r.price_per_share == 1.00
    assert r.round_shares == 5_000_000
    assert r.post_money_shares == 45_000_000
    assert r.effective_date == date(2026, 6, 1)
    assert r.reviewer == "Sarah Jenkins (Legal VP)"
    assert r.notes == "Lead investor: Sequoia"
    assert r.client_request_id is not None
    assert r.created_at is not None


def test_convertible_status_transitions(session):
    """Convertible status transitions: outstanding -> converted -> (can't go back)."""
    c = Convertible(
        id=str(uuid4()),
        issuer_name="Acme Corp",
        investor_name="VC Fund I",
        purchase_amount=1_000_000.0,
        currency="USD",
        instrument_kind="post_money_safe",
        valuation_cap=20_000_000.0,
        discount_rate=0.20,
        pro_rata_rights=None,
        mfn_clause=None,
        conversion_trigger="Equity financing",
        issued_date=date(2026, 1, 15),
        status=ConvertibleStatus.OUTSTANDING,
    )
    session.add(c)
    session.commit()

    # Mark as converted
    c.status = ConvertibleStatus.CONVERTED
    c.converted_at = datetime.now(timezone.utc)
    c.conversion_event_id = "evt_123"
    session.commit()
    session.refresh(c)

    assert c.status == ConvertibleStatus.CONVERTED
    assert c.converted_at is not None
    assert c.conversion_event_id == "evt_123"

    # Cancelled is also a terminal state
    c2 = Convertible(
        id=str(uuid4()),
        issuer_name="Acme Corp",
        investor_name="VC Fund II",
        purchase_amount=500_000.0,
        currency="USD",
        instrument_kind="post_money_safe",
        valuation_cap=15_000_000.0,
        discount_rate=0.15,
        pro_rata_rights=None,
        mfn_clause=None,
        conversion_trigger="Equity financing",
        issued_date=date(2026, 2, 1),
        status=ConvertibleStatus.CANCELLED,
    )
    session.add(c2)
    session.commit()
    session.refresh(c2)

    assert c2.status == ConvertibleStatus.CANCELLED