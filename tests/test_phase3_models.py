"""ORM round-trip tests for Phase 3.1 - Convertible and PricedRound models.

Acceptance: migration runs cleanly, models round-trip through the ORM.
"""
from datetime import date
from app.models.orm import Convertible, PricedRound
from app.models.enums import ConvertibleStatus


def test_convertible_roundtrip(session):
    c = Convertible(
        id="conv_1",
        issuer_name="Acme Corp",
        investor_name="VC Fund I",
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
    )
    session.add(c)
    session.commit()
    session.refresh(c)

    assert c.id == "conv_1"
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
    r = PricedRound(
        id="round_1",
        issuer_name="Acme Corp",
        round_name="Series A",
        price_per_share=1.00,
        round_shares=5_000_000,
        post_money_shares=45_000_000,
        effective_date=date(2026, 6, 1),
        reviewer="Sarah Jenkins (Legal VP)",
        notes="Lead: Sequoia",
        client_request_id="req_abc123",
    )
    session.add(r)
    session.commit()
    session.refresh(r)

    assert r.id == "round_1"
    assert r.issuer_name == "Acme Corp"
    assert r.round_name == "Series A"
    assert r.price_per_share == 1.00
    assert r.round_shares == 5_000_000
    assert r.post_money_shares == 45_000_000
    assert r.effective_date == date(2026, 6, 1)
    assert r.reviewer == "Sarah Jenkins (Legal VP)"
    assert r.notes == "Lead: Sequoia"
    assert r.client_request_id == "req_abc123"
    assert r.created_at is not None


def test_priced_round_unique_client_request_id(session):
    import pytest
    r1 = PricedRound(id="r1", issuer_name="Acme", round_name="A",
                     price_per_share=1.00, round_shares=100, post_money_shares=200,
                     effective_date=date(2026, 1, 1), reviewer="test",
                     client_request_id="dup")
    session.add(r1)
    session.commit()

    r2 = PricedRound(id="r2", issuer_name="Acme", round_name="B",
                     price_per_share=2.00, round_shares=100, post_money_shares=200,
                     effective_date=date(2026, 2, 1), reviewer="test",
                     client_request_id="dup")
    session.add(r2)
    with pytest.raises(Exception):
        session.commit()
