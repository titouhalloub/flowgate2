"""Tests for Phase 3.2-3.3 - SAFE conversion math.

compute_conversions mirrors app/captable.py. When the backend formula
changes, this must change in the same commit.
"""
import pytest
from app.captable import compute_conversions, ConversionError


def _safe(
    id="safe_1",
    investor_name="VC Fund I",
    purchase_amount=1_000_000,
    valuation_cap=20_000_000,
    discount_rate=0.20,
    instrument_kind="post_money_safe",
):
    return {
        "id": id,
        "investor_name": investor_name,
        "purchase_amount": purchase_amount,
        "valuation_cap": valuation_cap,
        "discount_rate": discount_rate,
        "instrument_kind": instrument_kind,
    }


# Test 1: Post-money SAFE, cap basis wins (round price $1.00)
def test_cap_basis_wins():
    r = compute_conversions([_safe()], round_price=1.00,
                            pre_safe_shares=40_000_000, options_pool=5_000_000)
    assert len(r) == 1
    res = r[0]
    assert res.investor_name == "VC Fund I"
    assert res.pricing_basis == "cap"
    assert res.shares_issued == pytest.approx(2_368_421.0526, rel=1e-4)
    assert res.cap_price == pytest.approx(0.4222, rel=1e-3)
    assert res.discount_price == pytest.approx(0.80)
    assert res.conversion_price == res.cap_price


# Test 2: Discount basis wins (round price $0.20)
def test_discount_basis_wins():
    r = compute_conversions([_safe()], round_price=0.20,
                            pre_safe_shares=40_000_000, options_pool=5_000_000)
    assert len(r) == 1
    res = r[0]
    assert res.pricing_basis == "discount"
    assert res.discount_price == pytest.approx(0.16)
    assert res.shares_issued == pytest.approx(6_250_000.0)
    assert res.conversion_price == pytest.approx(0.16)
    assert res.cap_price == pytest.approx(0.4222, rel=1e-3)


# Test 3: Equal prices -> cap wins (deterministic tie-break)
def test_tie_break_prefers_cap():
    r = compute_conversions([_safe()], round_price=0.5278,
                            pre_safe_shares=40_000_000, options_pool=5_000_000)
    assert r[0].pricing_basis == "cap"


# Test 4: No discount -> cap always wins
def test_no_discount_cap_only():
    r = compute_conversions([_safe(discount_rate=None)], round_price=0.05,
                            pre_safe_shares=40_000_000, options_pool=5_000_000)
    assert r[0].pricing_basis == "cap"
    assert r[0].discount_price == float("inf")


# Test 5: Multiple SAFEs don't dilute each other
def test_multiple_safes():
    r = compute_conversions(
        [_safe(id="safe_1", investor_name="Fund A"),
         _safe(id="safe_2", investor_name="Fund B", purchase_amount=2_000_000)],
        round_price=1.00,
        pre_safe_shares=40_000_000, options_pool=5_000_000)
    assert len(r) == 2
    assert r[0].investor_name == "Fund A"
    assert r[0].shares_issued == pytest.approx(2_647_058.82, rel=1e-4)
    assert r[0].cap_price == pytest.approx(0.3778, rel=1e-3)
    assert r[1].investor_name == "Fund B"
    assert r[1].shares_issued == pytest.approx(5_294_117.65, rel=1e-4)
    assert r[1].cap_price == pytest.approx(0.3778, rel=1e-3)


# Test 5b: Mixed basis across SAFEs - A on cap, B on discount
def test_mixed_basis():
    r = compute_conversions(
        [_safe(id="safe_1", investor_name="Fund A", discount_rate=None),
         _safe(id="safe_2", investor_name="Fund B", discount_rate=0.20)],
        round_price=0.20,
        pre_safe_shares=40_000_000, options_pool=5_000_000)
    assert len(r) == 2
    assert r[0].pricing_basis == "cap"
    assert r[1].pricing_basis == "discount"
    assert r[1].shares_issued == pytest.approx(6_250_000.0)


# Test 6: Error handling
def test_raises_on_invalid_round_price():
    with pytest.raises(ConversionError, match="round_price must be positive"):
        compute_conversions([_safe()], round_price=0,
                            pre_safe_shares=40_000_000, options_pool=5_000_000)


def test_raises_on_pre_money_safe():
    with pytest.raises(ConversionError, match="Pre-money SAFE"):
        compute_conversions([_safe(instrument_kind="pre_money_safe")],
                            round_price=1.00,
                            pre_safe_shares=40_000_000, options_pool=5_000_000)


def test_raises_on_over_concentrated_ownership():
    with pytest.raises(ConversionError, match="100%"):
        compute_conversions([_safe(valuation_cap=1_000_000)], round_price=1.00,
                            pre_safe_shares=40_000_000, options_pool=5_000_000)
