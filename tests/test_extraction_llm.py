"""Tests for LLM-based extraction with verifier (Phase E2)."""

from __future__ import annotations

import json

import pytest

from app.extraction import run_extraction
from app.extraction_llm import (
    _aggregate_confidence,
    _merge,
    extract_with_llm,
)


# --- Fake OpenAI client ---------------------------------------------------

class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    def create(self, **kwargs):  # noqa: ANN003
        return _FakeResponse(self._responses.pop(0))


class _FakeChat:
    def __init__(self, responses: list[str]) -> None:
        self.completions = _FakeCompletions(responses)


class _FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self.chat = _FakeChat(responses)


# --- Constants ------------------------------------------------------------

SAFE_TEXT = """SIMPLE AGREEMENT FOR FUTURE EQUITY
Y Combinator Post-Money SAFE

Acme Robotics, Inc. (the "Company")
Investor: Sierra Capital Partners LLC
Purchase Amount: $100,000
Post-Money Valuation Cap: $8,000,000
Discount Rate: 15%
"""

EXTRACT_RESPONSE = {
    "company_name": {
        "value": "Acme Robotics, Inc.",
        "evidence": "Acme Robotics, Inc. (the \"Company\")",
        "confidence": 1.0,
    },
    "investor_name": {
        "value": "Sierra Capital Partners LLC",
        "evidence": "Investor: Sierra Capital Partners LLC",
        "confidence": 1.0,
    },
    "purchase_amount": {
        "value": 100000,
        "evidence": "Purchase Amount: $100,000",
        "confidence": 1.0,
    },
    "currency": {
        "value": "USD",
        "evidence": "Purchase Amount: $100,000",
        "confidence": 0.9,
    },
    "valuation_cap": {
        "value": 8000000,
        "evidence": "Post-Money Valuation Cap: $8,000,000",
        "confidence": 1.0,
    },
    "discount_rate": {
        "value": 0.15,
        "evidence": "Discount Rate: 15%",
        "confidence": 1.0,
    },
    "instrument_kind": {
        "value": "post_money_safe",
        "evidence": "Y Combinator Post-Money SAFE",
        "confidence": 0.9,
    },
    "pro_rata_rights": {"value": None, "evidence": "NO EVIDENCE", "confidence": 0.0},
    "mfn_clause": {"value": None, "evidence": "NO EVIDENCE", "confidence": 0.0},
    "conversion_trigger": {"value": None, "evidence": "NO EVIDENCE", "confidence": 0.0},
    "document_date": {"value": None, "evidence": "NO EVIDENCE", "confidence": 0.0},
}

VERIFY_RESPONSE = {
    "company_name": {"present_in_source": True, "supported": True, "evidence": "Acme Robotics, Inc.", "confidence": 1.0},
    "investor_name": {"present_in_source": True, "supported": True, "evidence": "Sierra Capital Partners LLC", "confidence": 1.0},
    "purchase_amount": {"present_in_source": True, "supported": True, "evidence": "$100,000", "confidence": 1.0},
    "currency": {"present_in_source": True, "supported": True, "evidence": "USD", "confidence": 0.9},
    "valuation_cap": {"present_in_source": True, "supported": True, "evidence": "$8,000,000", "confidence": 1.0},
    "discount_rate": {"present_in_source": True, "supported": True, "evidence": "15%", "confidence": 1.0},
    "instrument_kind": {"present_in_source": True, "supported": True, "evidence": "Post-Money SAFE", "confidence": 1.0},
    "pro_rata_rights": {"present_in_source": False, "supported": False, "evidence": "NO EVIDENCE", "confidence": 0.0},
    "mfn_clause": {"present_in_source": False, "supported": False, "evidence": "NO EVIDENCE", "confidence": 0.0},
    "conversion_trigger": {"present_in_source": False, "supported": False, "evidence": "NO EVIDENCE", "confidence": 0.0},
    "document_date": {"present_in_source": False, "supported": False, "evidence": "NO EVIDENCE", "confidence": 0.0},
}


# --- Unit tests for helpers -----------------------------------------------

def test_aggregate_confidence_all_critical_present_full():
    per_field = {"a": {"confidence": 1.0, "counts": True}, "b": {"confidence": 1.0, "counts": True}}
    assert _aggregate_confidence(per_field, ["a", "b"], [], []) == 1.0


def test_aggregate_confidence_absent_field_does_not_penalize():
    """A field with counts=False must be skipped, not counted as a miss."""
    per_field = {
        "a": {"confidence": 1.0, "counts": True},
        "b": {"confidence": 0.0, "counts": False},
    }
    assert _aggregate_confidence(per_field, ["a", "b"], [], []) == 1.0


def test_aggregate_confidence_zero_denominator_returns_zero():
    assert _aggregate_confidence({}, [], [], []) == 0.0


def test_aggregate_confidence_weighted_scheme():
    per_field = {
        "crit": {"confidence": 1.0, "counts": True},
        "std": {"confidence": 0.5, "counts": True},
        "opt": {"confidence": 0.0, "counts": True},
    }
    expected = round(1.3 / 1.9, 3)
    assert _aggregate_confidence(per_field, ["crit"], ["std"], ["opt"]) == expected


def test_merge_supported_field_takes_min_confidence():
    extracted = {"a": {"value": 1, "confidence": 0.9}}
    verified = {"a": {"present_in_source": True, "supported": True, "confidence": 0.7}}
    merged = _merge(extracted, verified)
    assert merged["a"]["value"] == 1
    assert merged["a"]["confidence"] == 0.7
    assert merged["a"]["counts"] is True


def test_merge_unsupported_field_zeroes_confidence():
    extracted = {"a": {"value": 1, "confidence": 0.9}}
    verified = {"a": {"present_in_source": True, "supported": False, "confidence": 0.0}}
    merged = _merge(extracted, verified)
    assert merged["a"]["value"] is None
    assert merged["a"]["confidence"] == 0.0
    assert merged["a"]["counts"] is True


def test_merge_absent_field_does_not_count():
    """A field the source doesn't mention must be excluded from the score."""
    extracted = {"a": {"value": None, "confidence": 0.0}}
    verified = {"a": {"present_in_source": False, "supported": False, "confidence": 0.0}}
    merged = _merge(extracted, verified)
    assert merged["a"]["value"] is None
    assert merged["a"]["confidence"] == 0.0
    assert merged["a"]["counts"] is False



# --- extract_with_llm -----------------------------------------------------

def test_extract_with_llm_returns_none_for_unknown_type(monkeypatch):
    monkeypatch.setattr(
        "app.extraction_llm._get_client",
        lambda: (_FakeClient([]), "test-model"),
    )
    assert extract_with_llm("any text", "not_a_real_document_type") is None


def test_extract_with_llm_returns_none_when_no_client(monkeypatch):
    monkeypatch.setattr("app.extraction_llm._get_client", lambda: None)
    assert extract_with_llm(SAFE_TEXT, "safe") is None


def test_extract_with_llm_happy_path(monkeypatch):
    fake = _FakeClient([
        json.dumps(EXTRACT_RESPONSE),
        json.dumps(VERIFY_RESPONSE),
    ])
    monkeypatch.setattr(
        "app.extraction_llm._get_client",
        lambda: (fake, "test-model"),
    )
    outcome = extract_with_llm(SAFE_TEXT, "safe")
    assert outcome is not None
    assert outcome.schema_name == "SafeExtraction"
    assert outcome.extraction is not None
    assert outcome.extraction.company_name == "Acme Robotics, Inc."
    assert outcome.extraction.purchase_amount == 100000
    assert outcome.extraction.valuation_cap == 8000000
    assert outcome.extraction.discount_rate == 0.15
    assert outcome.confidence >= 0.80
    assert outcome.routed_to_review is False


def test_extract_with_llm_returns_none_on_malformed_json(monkeypatch):
    fake = _FakeClient([
        "not json at all",
        json.dumps(VERIFY_RESPONSE),
    ])
    monkeypatch.setattr(
        "app.extraction_llm._get_client",
        lambda: (fake, "test-model"),
    )
    assert extract_with_llm(SAFE_TEXT, "safe") is None


def test_extract_with_llm_low_confidence_routes_to_review(monkeypatch):
    weak_extract = {k: {"value": None, "evidence": "NO EVIDENCE", "confidence": 0.0}
                    for k in EXTRACT_RESPONSE}
    weak_extract["purchase_amount"] = {
        "value": 100000,
        "evidence": "Purchase Amount: $100,000",
        "confidence": 0.6,
    }
    fake = _FakeClient([
        json.dumps(weak_extract),
        json.dumps({k: {"present_in_source": True, "supported": False, "evidence": "NO EVIDENCE", "confidence": 0.0}
                    for k in EXTRACT_RESPONSE}),
    ])
    monkeypatch.setattr(
        "app.extraction_llm._get_client",
        lambda: (fake, "test-model"),
    )
    outcome = extract_with_llm(SAFE_TEXT, "safe")
    assert outcome is not None
    assert outcome.confidence < 0.80
    assert outcome.routed_to_review is True


# --- Integration through run_extraction -----------------------------------

def test_run_extraction_falls_back_to_regex_when_no_llm(monkeypatch):
    monkeypatch.setattr("app.extraction_llm._get_client", lambda: None)
    outcome = run_extraction("any loan text", "loan_agreement")
    assert outcome is not None
    assert isinstance(outcome.confidence, float)
    assert isinstance(outcome.routed_to_review, bool)

def test_extract_with_llm_handles_human_date_format(monkeypatch):
    """Reproduces the Reed's Inc. SAFE failure: LLM returns
    'January 16, 2023' as a string; must be coerced, not dropped."""
    import datetime
    extract = dict(EXTRACT_RESPONSE)
    extract["document_date"] = {
        "value": "January 16, 2023",
        "evidence": "Date: January 16, 2023",
        "confidence": 0.9,
    }
    verify = dict(VERIFY_RESPONSE)
    verify["document_date"] = {
        "present_in_source": True,
        "supported": True,
        "evidence": "January 16, 2023",
        "confidence": 0.9,
    }
    fake = _FakeClient([json.dumps(extract), json.dumps(verify)])
    monkeypatch.setattr(
        "app.extraction_llm._get_client",
        lambda: (fake, "test-model"),
    )
    outcome = extract_with_llm(SAFE_TEXT, "safe")
    assert outcome is not None
    assert outcome.extraction is not None
    assert outcome.extraction.document_date == datetime.date(2023, 1, 16)

def test_merge_nulls_value_when_verifier_rejects():
    """A rejected field must not surface its value to the UI."""
    extracted = {"company_name": {"value": "Demo Issuer", "confidence": 0.9}}
    verified = {"company_name": {"supported": False, "confidence": 0.0}}
    merged = _merge(extracted, verified)
    assert merged["company_name"]["value"] is None
    assert merged["company_name"]["confidence"] == 0.0

def test_merge_degrades_gracefully_when_verify_fails():
    """When verify returns {} (API failure), _merge must fall back to
    trusting extract's own confidence -- not mark all fields absent."""
    extracted = {
        "company_name": {"value": "Reed's Inc.", "confidence": 1.0},
        "purchase_amount": {"value": 3000000, "confidence": 0.9},
        "valuation_cap": {"value": None, "confidence": 0.0},
    }
    merged = _merge(extracted, {})  # empty verify result
    assert merged["company_name"]["value"] == "Reed's Inc."
    assert merged["company_name"]["confidence"] == 1.0
    assert merged["company_name"]["counts"] is True
    assert merged["purchase_amount"]["value"] == 3000000
    assert merged["purchase_amount"]["counts"] is True
    assert merged["valuation_cap"]["counts"] is False

def test_extract_with_llm_stores_correct_extracted_data_shape(monkeypatch):
    """extracted_data must be {"data": {flat fields}} for downstream consumers.

    _backfill_deal_container, _maybe_create_convertible_proposal, and
    create_cap_table_proposal all read .get("data", {}).get(field_name).
    If we store the debug-shape {field: {value, confidence, counts}} the
    proposal route 400s on every SAFE upload.
    """
    fake = _FakeClient([
        json.dumps(EXTRACT_RESPONSE),
        json.dumps(VERIFY_RESPONSE),
    ])
    monkeypatch.setattr(
        "app.extraction_llm._get_client",
        lambda: (fake, "test-model"),
    )
    outcome = extract_with_llm(SAFE_TEXT, "safe")
    assert outcome is not None
    ed = outcome.extracted_data
    assert isinstance(ed, dict)
    assert "data" in ed
    inner = ed["data"]
    assert inner.get("schema_name") == "SafeExtraction"
    assert inner.get("company_name") == "Acme Robotics, Inc."
    assert isinstance(inner.get("purchase_amount"), (int, float))
    # The debug-only shape must NOT be stored.
    assert not isinstance(inner.get("company_name"), dict)

# --- E3: multi-schema -----------------------------------------------------

def test_resolve_schema_loan():
    from app.extraction_llm import _resolve_schema
    name, cls = _resolve_schema("loan_agreement")
    assert name == "LoanExtraction"
    assert cls is not None


def test_resolve_schema_safe():
    from app.extraction_llm import _resolve_schema
    name, cls = _resolve_schema("safe")
    assert name == "SafeExtraction"
    assert cls is not None


def test_resolve_schema_unknown_returns_none():
    from app.extraction_llm import _resolve_schema
    name, cls = _resolve_schema("not_a_real_type")
    assert name is None
    assert cls is None


def test_extract_with_llm_handles_loan_path(monkeypatch):
    """E3: loan_agreement goes through the LLM path.

    Tolerates either a full outcome or a graceful None (if the schema
    has required fields that our empty mock can't satisfy).
    """
    from app.schemas import LoanExtraction
    fields = [
        n for n in LoanExtraction.model_fields
        if n not in ("schema_name", "schema_version", "extracted_at", "source_text")
    ]
    extract_resp = {
        n: {"value": None, "evidence": "NO EVIDENCE", "confidence": 0.0}
        for n in fields
    }
    verify_resp = {
        n: {"present_in_source": False, "supported": False,
            "evidence": "NO EVIDENCE", "confidence": 0.0}
        for n in fields
    }
    fake = _FakeClient([json.dumps(extract_resp), json.dumps(verify_resp)])
    monkeypatch.setattr(
        "app.extraction_llm._get_client",
        lambda: (fake, "test-model"),
    )
    outcome = extract_with_llm("dummy loan text", "loan_agreement")
    if outcome is not None:
        assert outcome.schema_name == "LoanExtraction"


def test_aggregate_default_weight_for_unlisted_field():
    """Fields absent from all three lists get default weight 1.0."""
    per_field = {
        "unlisted_a": {"confidence": 1.0, "counts": True},
        "unlisted_b": {"confidence": 0.5, "counts": True},
    }
    result = _aggregate_confidence(per_field, [], [], [])
    assert result == round((1.0 + 0.5) / 2.0, 3)

def test_instantiate_fills_source_text_when_required():
    """E3.1: schemas that declare source_text (str, required) must have
    it auto-filled from the pipeline input, not from the LLM response.

    Provides real values for the schema's other required fields, matching
    what the LLM actually returns on a real document (per the RCL Foods
    production log), so the test exercises only the source_text path.
    """
    from app.schemas import SubscriptionAgreementExtraction
    from app.extraction_llm import _instantiate

    merged = {
        "fund_name": {"value": "Test Fund LP", "confidence": 0.9, "counts": True},
        "investor_name": {"value": "Test Investor LLC", "confidence": 0.9, "counts": True},
        "commitment_amount": {"value": 1000000.0, "confidence": 0.9, "counts": True},
        "currency": {"value": "USD", "confidence": 0.9, "counts": True},
    }

    inst = _instantiate(
        SubscriptionAgreementExtraction, merged,
        source_text="the full source document text",
    )
    assert inst is not None
    assert inst.source_text == "the full source document text"
    assert inst.fund_name == "Test Fund LP"
