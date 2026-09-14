"""SAFE (Simple Agreement for Future Equity) support: classification lexicon,
heuristic wiring, LLM vocabulary, extractor registration, and field extraction.

Spec: CAPTABLE-ROADMAP-FEATURES.md -- SAFE documents must classify as SAFE,
route to ``extract_safe``, and populate the typed SafeExtraction fields.
"""
import inspect

from app.classification import (
    _classify_with_openai_compatible,
    _parse_llm_document_type,
    classify_with_heuristics,
)
from app.extraction import extract_safe, run_extraction
from app.models.enums import DocumentType
from app.schemas import SafeExtraction

# Mirrors a YC post-money SAFE: purchase amount, post-money valuation cap,
# discount rate, pro-rata rights, MFN, and the priced-round trigger.
SAFE_TEXT = """SIMPLE AGREEMENT FOR FUTURE EQUITY
Y Combinator Post-Money SAFE

Acme Robotics, Inc. (the "Company")

The Investor: Sierra Capital Partners LLC

Purchase Amount: $100,000
Post-Money Valuation Cap: $8,000,000
Discount Rate: 15%
Pro-Rata Rights: The Investor shall have pro-rata rights
MFN: This SAFE includes a Most Favored Nation clause

This SAFE is convertible upon the closing of a Priced Equity Round
(liquidity capitalization) or a dissolution event.
"""


def test_safe_heuristic_classifies():
    result = classify_with_heuristics(SAFE_TEXT, filename="yc_safe.pdf")
    assert result.document_type == DocumentType.SAFE
    assert result.confidence >= 0.75


def test_llm_parse_accepts_safe():
    assert _parse_llm_document_type("safe") == DocumentType.SAFE


def test_llm_prompt_vocabulary_includes_safe():
    """Guard: the LLM classifier's allowed output vocabulary must contain
    ``safe`` or a SAFE lands on the nearest wrong bucket."""
    source = inspect.getsource(_classify_with_openai_compatible)
    assert "safe" in source


def test_safe_extraction_populates_all_fields():
    outcome = run_extraction(SAFE_TEXT, DocumentType.SAFE.value)
    assert outcome.schema_name == "SafeExtraction"
    assert outcome.extraction is not None
    assert isinstance(outcome.extraction, SafeExtraction)
    assert not outcome.routed_to_review

    x = outcome.extraction
    assert x.company_name == "Acme Robotics, Inc."
    assert x.investor_name == "Sierra Capital Partners LLC"
    assert x.purchase_amount == 100_000.0
    assert x.valuation_cap == 8_000_000.0
    assert x.discount_rate == 0.15  # fractional, per the schema contract
    assert x.pro_rata_rights is True
    assert x.mfn_clause is True
    assert x.instrument_kind == "post_money_safe"

    data = outcome.extracted_data["data"]
    assert data["schema_name"] == "SafeExtraction"
    assert data["schema_version"] == "v1"
    assert data["discount_rate"] == 0.15


def test_safe_extraction_silence_maps_to_none():
    """Explicit-marks-only rule: no pro-rata / MFN / flavor language in the
    document must yield None (unknown), not a guessed True/post-money."""
    text = """SIMPLE AGREEMENT FOR FUTURE EQUITY
Quiet Labs, Inc. (the "Company")
Purchase Amount: $25,000
Valuation Cap: $5,000,000
"""
    extraction, _conf = extract_safe(text)
    assert extraction is not None
    assert extraction.pro_rata_rights is None
    assert extraction.mfn_clause is None
    assert extraction.instrument_kind is None
    assert extraction.valuation_cap == 5_000_000.0
    assert extraction.purchase_amount == 25_000.0
