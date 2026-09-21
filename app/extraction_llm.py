"""LLM-based extraction with verifier (Phase E2).

Two OpenAI-compatible calls per document:
  1. _call_extract — pull per-field {value, evidence, confidence}.
  2. _call_verify  — re-check each value against the source.

Per-field confidence is min(extract, verify), or 0.0 when the
verifier marks the field unsupported. The aggregate is a weighted
mean using the same 1.0 / 0.6 / 0.3 weights the regex extractors
use, so the numeric range stays comparable.

E2 scope: SafeExtraction only. Other document types fall through to
the regex extractor via extract_with_llm returning None.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from app.config import settings

if TYPE_CHECKING:
    from app.extraction import ExtractionOutcome

logger = logging.getLogger(__name__)


SAFE_CRITICAL = ["company_name", "purchase_amount", "valuation_cap", "currency"]
SAFE_STANDARD = ["investor_name", "instrument_kind", "discount_rate"]
SAFE_OPTIONAL = ["pro_rata_rights", "mfn_clause", "conversion_trigger", "document_date"]


def _get_client() -> tuple[Any, str] | None:
    """Return (openai_client, model) for the preferred backend, or None.
    Tests monkeypatch this to inject a fake client."""
    api_key = settings.openrouter_api_key
    if not api_key:
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None
    client = OpenAI(
        api_key=api_key,
        base_url=settings.openrouter_base_url,
        timeout=55.0,
    )
    return client, settings.openrouter_model


def extract_with_llm(text: str, document_type: str) -> "ExtractionOutcome | None":
    """Try LLM extraction for a supported document type.
    Return None on any failure so the regex extractor runs unchanged."""
    if document_type != "safe":
        return None  # E3 expands to the remaining schemas

    resolved = _get_client()
    if resolved is None:
        return None
    client, model = resolved

    try:
        extracted = _call_extract(client, model, text)
        if not extracted:
            return None
        verified = _call_verify(client, model, text, extracted)
        merged = _merge(extracted, verified)
        confidence = _aggregate_confidence(
            merged, SAFE_CRITICAL, SAFE_STANDARD, SAFE_OPTIONAL
        )
        instance = _instantiate_safe(merged)
        if instance is None:
            return None
        from app.extraction import ExtractionOutcome
        return ExtractionOutcome(
            schema_name="SafeExtraction",
            schema_version="v1",
            extraction=instance,
            confidence=confidence,
            routed_to_review=confidence < settings.extraction_llm_min_confidence,
            extracted_data=merged,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM extraction failed, falling back to regex: %s", exc)
        return None


def _call_extract(client: Any, model: str, text: str) -> dict[str, Any] | None:
    from app.schemas import SafeExtraction

    schema = SafeExtraction.model_json_schema()
    properties = schema.get("properties", {})
    field_list = [
        f for f in properties
        if f not in ("schema_name", "schema_version", "extracted_at", "source_text")
    ]

    system = (
        "You extract structured data from Y Combinator SAFE "
        "(Simple Agreement for Future Equity) documents.\n\n"
        "Return ONLY valid JSON. For every field below, output an object:\n"
        '  {"value": <extracted value or null>,\n'
        '   "evidence": "<verbatim substring from the source, or NO EVIDENCE>",\n'
        '   "confidence": <0.0 to 1.0>}\n\n'
        "Confidence rules:\n"
        "  1.0 = exact match, verbatim in the source\n"
        "  0.8 = minor normalization (e.g. 15% -> 0.15, $3M -> 3000000)\n"
        "  0.5 = inferred or ambiguous\n"
        "  0.0 = not present or no evidence\n\n"
        "Never guess. If a field is absent, use null with evidence "
        "'NO EVIDENCE'. Do not invent values. Do not fill fields from context.\n\n"
        "Fields to extract:\n" + "\n".join(f"  - {f}" for f in field_list) + "\n\n"
        "Return JSON only, no explanation."
    )
    user = f"Document text:\n\n{text}\n\nReturn the JSON now."

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,
    )
    content = resp.choices[0].message.content
    data = json.loads(content)
    if not isinstance(data, dict):
        return None
    return data


def _call_verify(
    client: Any,
    model: str,
    text: str,
    extracted: dict[str, Any],
) -> dict[str, Any]:
    fields_only = {
        k: v.get("value")
        for k, v in extracted.items()
        if isinstance(v, dict)
    }

    system = (
        "You are a fact-checker. Given a document and a set of extracted "
        "fields, verify whether the source supports each extracted value.\n\n"
        "Return ONLY valid JSON. For every field, output:\n"
        '  {"supported": true or false,\n'
        '   "evidence": "<verbatim source snippet, or NO EVIDENCE>",\n'
        '   "confidence": <0.0 to 1.0>}\n\n'
        "Be strict. If the source does not literally contain the value or "
        "a clear paraphrase, mark supported=false with confidence 0.0. Do "
        "not accept plausible-sounding values that are not grounded.\n\n"
        "Return JSON only, no explanation."
    )
    user = (
        f"Source document:\n\n{text}\n\n"
        f"Extracted values to verify:\n\n"
        f"{json.dumps(fields_only, indent=2, default=str)}\n\n"
        f"Verify each field."
    )

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,
    )
    content = resp.choices[0].message.content
    data = json.loads(content)
    if not isinstance(data, dict):
        return {}
    return data


def _merge(
    extracted: dict[str, Any],
    verified: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Combine extract + verify: min(confidence) if supported, else 0.0."""
    merged: dict[str, dict[str, Any]] = {}
    for field, e in extracted.items():
        if not isinstance(e, dict):
            continue
        v = verified.get(field, {})
        if not isinstance(v, dict) or not v.get("supported", False):
            merged[field] = {"value": e.get("value"), "confidence": 0.0}
            continue
        try:
            ext_conf = float(e.get("confidence", 0.0))
            ver_conf = float(v.get("confidence", 0.0))
        except (TypeError, ValueError):
            ext_conf, ver_conf = 0.0, 0.0
        merged[field] = {
            "value": e.get("value"),
            "confidence": min(ext_conf, ver_conf),
        }
    return merged


def _instantiate_safe(merged: dict[str, dict[str, Any]]):
    from app.schemas import SafeExtraction
    try:
        kwargs = {
            k: merged[k]["value"]
            for k in merged
            if merged[k].get("value") is not None
        }
        return SafeExtraction(**kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("SafeExtraction validation failed: %s", exc)
        return None


def _aggregate_confidence(
    per_field: dict[str, dict[str, Any]],
    critical: list[str],
    standard: list[str],
    optional: list[str],
) -> float:
    def _sum(fields: list[str], weight: float) -> float:
        return weight * sum(
            float(per_field.get(f, {}).get("confidence", 0.0)) for f in fields
        )

    num = _sum(critical, 1.0) + _sum(standard, 0.6) + _sum(optional, 0.3)
    den = 1.0 * len(critical) + 0.6 * len(standard) + 0.3 * len(optional)
    if den == 0:
        return 0.0
    return round(min(1.0, num / den), 3)
