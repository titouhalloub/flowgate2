"""Tests for the classifier-rescue path (E2.9).

The classifier is a hint, not a gate: when it says UNCLASSIFIED but
the filename names a type and extraction confirms it, the document
processes. These tests pin the filename-inference helper.
"""

from __future__ import annotations

from app.models.enums import DocumentType
from app.pipeline import _guess_type_from_filename


def test_safe_from_filename():
    assert _guess_type_from_filename("Reed's-SAFE.pdf") == DocumentType.SAFE
    assert _guess_type_from_filename("clerky_safe_v3.pdf") == DocumentType.SAFE
    assert _guess_type_from_filename("SIMPLE AGREEMENT FOR FUTURE EQUITY (SAFE).pdf") == DocumentType.SAFE


def test_sukuk_from_filename():
    assert _guess_type_from_filename("sukuk-al-ijara.pdf") == DocumentType.SUKUK_CERTIFICATE


def test_loan_from_filename():
    assert _guess_type_from_filename("term-loan-2024.pdf") == DocumentType.LOAN_AGREEMENT


def test_equity_subscription_beats_plain_subscription():
    assert (
        _guess_type_from_filename("equity-subscription-agreement.pdf")
        == DocumentType.EQUITY_SUBSCRIPTION
    )
    assert (
        _guess_type_from_filename("fund-subscription-agreement.pdf")
        == DocumentType.SUBSCRIPTION_AGREEMENT
    )


def test_capital_call_from_filename():
    assert (
        _guess_type_from_filename("capital-call-notice-q3.pdf")
        == DocumentType.CAPITAL_CALL_NOTICE
    )


def test_unknown_filename_returns_none():
    assert _guess_type_from_filename("scan-001.pdf") is None
    assert _guess_type_from_filename("") is None
    assert _guess_type_from_filename(None) is None


def test_case_insensitive():
    assert _guess_type_from_filename("SAFE.PDF") == DocumentType.SAFE
    assert _guess_type_from_filename("Safe.Pdf") == DocumentType.SAFE
