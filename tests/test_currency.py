"""Tests for currency detection (app/currency.py)."""

from app.currency import detect_currency, normalize_currency


def test_rand_with_space():
    assert detect_currency("the amount equal to R 300,767,092") == "ZAR"


def test_rand_no_space():
    assert detect_currency("R300,000,000") == "ZAR"


def test_us_dollar_symbol():
    assert detect_currency("Purchase Amount: $100,000") == "USD"


def test_us_dollar_prefixed():
    assert detect_currency("US$ 3,000,000") == "USD"


def test_euro():
    assert detect_currency("Subscription Price: \u20ac1,500,000") == "EUR"


def test_pound():
    assert detect_currency("GBP \u00a3500,000 payable") == "GBP"


def test_explicit_iso_code():
    assert detect_currency("Denominated in ZAR") == "ZAR"
    assert detect_currency("Amount: 1000000 EUR") == "EUR"


def test_brazilian_real():
    assert detect_currency("R$ 1,000,000") == "BRL"


def test_yen():
    assert detect_currency("\u00a5 500,000") == "JPY"


def test_indian_rupee():
    assert detect_currency("\u20b9 10,00,000") == "INR"
    assert detect_currency("Rs. 10,00,000") == "INR"


def test_swiss_franc():
    assert detect_currency("CHF 1,000,000") == "CHF"


def test_currency_name_in_prose():
    assert detect_currency("three hundred million Rand") == "ZAR"
    assert detect_currency("denominated in Swiss Francs") == "CHF"


def test_none_when_no_signal():
    assert detect_currency("no monetary amount here") is None
    assert detect_currency("") is None
    assert detect_currency(None) is None


def test_no_false_match_reed():
    assert detect_currency("Reed's Inc. issued the shares") is None


def test_no_false_match_revenue():
    assert detect_currency("Revenue increased 10%") is None


def test_normalize_from_value():
    assert normalize_currency("ZAR") == "ZAR"
    assert normalize_currency("zar") == "ZAR"
    assert normalize_currency("rand") == "ZAR"
    assert normalize_currency("Rand") == "ZAR"


def test_normalize_falls_back_to_text():
    assert normalize_currency(None, "the price is R 100") == "ZAR"
    assert normalize_currency("", "amount: $500") == "USD"


def test_iso_code_takes_precedence_over_symbol():
    assert detect_currency("ZAR 300,000 (R 300,000)") == "ZAR"
