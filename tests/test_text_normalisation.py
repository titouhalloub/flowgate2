"""Tests for the pre-extraction text normalisation (app/pipeline.py)."""

from app.pipeline import _normalise_raw_text
from app.extraction import extract_safe


def test_smart_apostrophe_is_normalised():
    """Curly apostrophe U+2019 becomes straight, so name regexes match."""
    raw = "Reed\u2019s Inc. (the \u201cCompany\u201d)"
    normalised = _normalise_raw_text(raw)
    assert "\u2019" not in normalised
    assert "'" in normalised
    assert "Reed's Inc." in normalised
    # Curly double quotes also normalised
    assert "\u201c" not in normalised
    assert "\u201d" not in normalised


def test_latex_delimiters_are_stripped():
    """LaTeX math delimiters become spaces; numbers stay intact."""
    raw = "of \\( 10,000.00\\(the \"Purchase Amount\")"
    normalised = _normalise_raw_text(raw)
    assert "\\(" not in normalised
    assert "\\)" not in normalised
    assert "10,000.00" in normalised
    # No double spaces should remain
    assert "  " not in normalised


def test_extract_safe_finds_amount_before_keyword_after_normalisation():
    """End-to-end: a Clerky-shape SAFE with LaTeX-mangled $ yields the
    purchase amount even though the amount precedes the label."""
    raw = (
        "POST-MONEY VALUATION CAP WITH DISCOUNT\n"
        "Acme Robotics, Inc. (the \"Company\")\n"
        "Carlethia Pratt (the \"Investor\")\n"
        "in exchange for payment of \\( 10,000.00\\(the \"Purchase Amount\")\n"
        "Post-Money Valuation Cap: \\( 2,500,000\n"
        "Discount Rate: 90%\n"
    )
    normalised = _normalise_raw_text(raw)
    extraction, confidence = extract_safe(normalised)
    assert extraction is not None
    assert extraction.purchase_amount == 10000.0
    assert extraction.company_name is not None
    assert "Acme" in extraction.company_name


def test_money_after_does_not_cross_newline_for_bare_numbers():
    """A bare number on the line after the keyword must not be captured.

    Regression guard: before this fix, _money_after's bare-number fallback
    scanned an 80-char forward window that often spanned a newline, so a
    'Purchase Amount' label followed by 'Valuation Cap: 2,500,000' on the
    next line returned 2,500,000 as the purchase amount.
    """
    from app.extraction import _money_after
    text = (
        "in exchange for payment of 10,000.00 the Purchase Amount)\n"
        "Post-Money Valuation Cap: 2,500,000\n"
    )
    amount, _ = _money_after(text, r"purchase\s+amount", window=80)
    assert amount is None, (
        f"_money_after should not cross the newline to grab the cap; got {amount}"
    )
