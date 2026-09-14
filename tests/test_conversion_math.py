"""Tests for Phase 3.2 — single SAFE conversion math.

Vesting math mirrors app/captable.py. When the backend formula changes,
this must change in the same commit.
"""
import pytest
from app.captable import compute_conversions, ConversionError


def _safe(
    id: str = "safe_1",
    investor_name: str = "VC Fund I",
    purchase_amount: float = 1_000_000,
    valuation_cap: float = 20_000_000,
    discount_rate: float | None = 0.20,
    instrument_kind: str = "post_money_safe",
):
    return {
        "id": id,
        "investor_name": investor_name,
        "purchase_amount": purchase_amount,
        "valuation_cap": valuation_cap,
        "discount_rate": discount_rate,
        "instrument_kind": instrument_kind,
    }


# --------------------------------------------------------------------------- #
# Test 1: Post-money SAFE, cap basis wins (round price $1.00)
# --------------------------------------------------------------------------- #


def test_cap_basis_wins():
    r = compute_conversions([_safe()], round_price=1.00,
                            pre_safe_shares=40_000_000, options_pool=5_000_000)
    assert len(r) == 1
    res = r[0]
    assert res.investor_name == "VC Fund I"
    assert res.pricing_basis == "cap"
    # owner_i = 1M / 20M = 0.05; sum = 0.05; shares = 0.05/0.95 * 45M
    assert res.shares_issued == pytest.approx(2_368_421.0526, rel=1e-4)
    # cap_price = 1M / shares = ~0.4222
    assert res.cap_price == pytest.approx(0.4222, rel=1e-3)
    # discount_price = 1.00 * 0.80 = 0.80 (higher, so not chosen)
    assert res.discount_price == pytest.approx(0.80)
    assert res.conversion_price == res.cap_price


# --------------------------------------------------------------------------- #
# Test 2: Discount basis wins (round price $0.20)
# --------------------------------------------------------------------------- #


def test_discount_basis_wins():
    r = compute_conversions([_safe()], round_price=0.20,
                            pre_safe_shares=40_000_000, options_pool=5_000_000)
    assert len(r) == 1
    res = r[0]
    assert res.pricing_basis == "discount"
    # discount_price = 0.20 * 0.80 = 0.16
    assert res.discount_price == pytest.approx(0.16)
    # shares = 1M / 0.16 = 6,250,000
    assert res.shares_issued == pytest.approx(6_250_000.0)
    assert res.conversion_price == pytest.approx(0.16)
    # cap_price unchanged (~0.4222, higher, so not chosen)
    assert res.cap_price == pytest.approx(0.4222, rel=1e-3)


# --------------------------------------------------------------------------- #
# Test 3: Equal prices → cap wins (tie-break is deterministic)
# --------------------------------------------------------------------------- #
def test_tie_break_prefers_cap():
    # round_price = 0.5278 → discount_price = 0.5278*0.8 = 0.4222 = cap_price
    r = compute_conversions([_safe()], round_price=0.5278,
                            pre_safe_shares=40_000_000, options_pool=5_000_000)
    assert r[0].pricing_basis == "cap"


# --------------------------------------------------------------------------- #
# Test 4: No discount → cap always wins
# --------------------------------------------------------------------------- #
def test_no_discount_cap_only():
    r = compute_conversions([_safe(discount_rate=None)], round_price=0.05,
                            pre_safe_shares=40_000_000, options_pool=5_000_000)
    assert r[0].pricing_basis == "cap"
    assert r[0].discount_price == float("inf")


# --------------------------------------------------------------------------- #
# Test 5: Multiple SAFEs don't dilute each other
# --------------------------------------------------------------------------- #
def test_multiple_safes():
    r = compute_conversions(
        [_safe(id="safe_1", investor_name="Fund A"),
         _safe(id="safe_2", investor_name="Fund B", purchase_amount=2_000_000)],
        round_price=1.00,
        pre_safe_shares=40_000_000, options_pool=5_000_000)
    assert len(r) == 2
    # Fund A: owner=0.05, Fund B: owner=2M/20M=0.10, sum=0.15
    # A shares = 0.05/0.85 * 45M = 2,647,059; cap_price = 1M/2.647M = 0.3778
    assert r[0].investor_name == "Fund A"
    assert r[0].shares_issued == pytest.approx(2_647_058.82, rel=1e-4)
    assert r[0].cap_price == pytest.approx(0.3778, rel=1e-3)
    # B shares = 0.10/0.85 * 45M = 5,294,118; cap_price = 2M/5.294M = 0.3778
    assert r[1].investor_name == "Fund B"
    assert r[1].shares_issued == pytest.approx(5_294_117.65, rel=1e-4)
    assert r[1].cap_price == pytest.approx(0.3778, rel=1e-3)


# --------------------------------------------------------------------------- #
# Test 6: Error handling
# --------------------------------------------------------------------------- #
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
    # cap = purchase, so owner = 1M/1M = 1.0, sum = 1.0 → should raise
    with pytest.raises(ConversionError, match="100%"):
        compute_conversions([_safe(valuation_cap=1_000_000)], round_price=1.00,
                            pre_safe_shares=40_000_000, options_pool=5_000_000)
