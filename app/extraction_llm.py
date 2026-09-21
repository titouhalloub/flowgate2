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
from datetime import date, datetime
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
    except Exception as exc:  # noqa: BLE001
        logger.exception("LLM stage=extract raised: %s", exc)
        return None
    if not extracted:
        logger.warning("LLM stage=extract returned empty")
        return None

    try:
        verified = _call_verify(client, model, text, extracted)
    except Exception as exc:  # noqa: BLE001
        logger.exception("LLM stage=verify raised: %s", exc)
        return None

    try:
        merged = _merge(extracted, verified)
        logger.info("extracted=%s", json.dumps(extracted, default=str)[:800])
        logger.info("verified=%s", json.dumps(verified, default=str)[:800])
        logger.info("merged=%s", json.dumps(merged, default=str)[:800])
    except Exception as exc:  # noqa: BLE001
        logger.exception("LLM stage=merge raised: %s", exc)
        return None

    try:
        instance = _instantiate_safe(merged)
    except Exception as exc:  # noqa: BLE001
        logger.exception("LLM stage=instantiate raised: %s", exc)
        return None
    if instance is None:
        return None

    try:
        confidence = _aggregate_confidence(
            merged, SAFE_CRITICAL, SAFE_STANDARD, SAFE_OPTIONAL
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("LLM stage=aggregate raised: %s", exc)
        return None

    from app.extraction import ExtractionOutcome

    try:
        return ExtractionOutcome(
            schema_name="SafeExtraction",
            schema_version="v1",
            extraction=instance,
            confidence=confidence,
            routed_to_review=confidence < settings.extraction_llm_min_confidence,
            extracted_data=merged,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("LLM stage=outcome raised: %s", exc)
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
    if resp is None:
        logger.warning("extract: OpenRouter returned None")
        return None
    choices = getattr(resp, "choices", None)
    if not choices:
        logger.warning("extract: response has no choices: %r", resp)
        return None
    msg = getattr(choices[0], "message", None)
    if msg is None:
        logger.warning("extract: choices[0].message is None")
        return None
    content = getattr(msg, "content", None)
    if not content:
        logger.warning("extract: message.content is empty")
        return None
    logger.info("extract: content length=%d", len(content))
    try:
        data = json.loads(content)
    except Exception as exc:  # noqa: BLE001
        logger.warning("extract: JSON parse failed: %s | head=%r", exc, content[:200])
        return None
    if not isinstance(data, dict):
        logger.warning("extract: parsed JSON is not a dict: %r", type(data))
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
        "fields, determine for each field:\n"
        "  1. Does the source document mention this field at all?\n"
        "  2. If yes, does the extracted value match what the source says?\n\n"
        "Return ONLY valid JSON. For every field, output:\n"
        '  {"present_in_source": true or false,\n'
        '   "supported": true or false,\n'
        '   "evidence": "<verbatim source snippet, or NO EVIDENCE>",\n'
        '   "confidence": <0.0 to 1.0>}\n\n'
        "Rules:\n"
        "  - present_in_source=false when the source contains NO information "
        "about this field (e.g. a SAFE with no valuation cap). Set "
        "supported=false, confidence 0.0 in that case.\n"
        "  - present_in_source=true when the source explicitly states this "
        "field.\n"
        "  - supported=true ONLY when the extracted value matches the "
        "source. supported=false when the value is a hallucination or "
        "does not appear in the source.\n"
        "Be strict. Do not accept plausible-sounding values that are not "
        "grounded in the source.\n\n"
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
    if resp is None:
        logger.warning("verify: OpenRouter returned None")
        return {}
    choices = getattr(resp, "choices", None)
    if not choices:
        logger.warning("verify: response has no choices")
        return {}
    msg = getattr(choices[0], "message", None)
    if msg is None:
        logger.warning("verify: choices[0].message is None")
        return {}
    content = getattr(msg, "content", None)
    if not content:
        logger.warning("verify: message.content is empty")
        return {}
    logger.info("verify: content length=%d", len(content))
    try:
        data = json.loads(content)
    except Exception as exc:  # noqa: BLE001
        logger.warning("verify: JSON parse failed: %s | head=%r", exc, content[:200])
        return {}
    if not isinstance(data, dict):
        logger.warning("verify: parsed JSON is not a dict")
        return {}
    return data


def _merge(
    extracted: dict[str, Any],
    verified: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Combine extract + verify.

    Each merged entry carries a `counts` flag:
      - counts=False: field is not present in the source; excluded from
        the confidence aggregate (a SAFE with no valuation cap is not
        a failure).
      - counts=True: field is present in the source; its confidence
        contributes to the aggregate.
    """
    merged: dict[str, dict[str, Any]] = {}
    for field, e in extracted.items():
        if not isinstance(e, dict):
            continue
        v = verified.get(field, {})
        if not isinstance(v, dict):
            v = {}

        present = bool(v.get("present_in_source", False))
        supported = bool(v.get("supported", False))

        if not present:
            # Field genuinely absent from the source. Not a miss.
            merged[field] = {"value": None, "confidence": 0.0, "counts": False}
            continue

        if not supported or e.get("value") is None:
            # Present in source but not extracted, or hallucinated.
            merged[field] = {"value": None, "confidence": 0.0, "counts": True}
            continue

        try:
            ext_conf = float(e.get("confidence", 0.0))
            ver_conf = float(v.get("confidence", 0.0))
        except (TypeError, ValueError):
            ext_conf, ver_conf = 0.0, 0.0
        merged[field] = {
            "value": e.get("value"),
            "confidence": min(ext_conf, ver_conf),
            "counts": True,
        }
    return merged


def _coerce_date_string(value: Any) -> Any:
    """Coerce an LLM-returned date string to a date object.
    Returns None when the string cannot be parsed."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return value
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y",
                "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _instantiate_safe(merged: dict[str, dict[str, Any]]):
    """Build a SafeExtraction from merged fields.
    Coerces date strings; drops fields pydantic rejects rather than
    abandoning the whole extraction. Mutates merged in place so the
    aggregate confidence reflects any drops."""
    from app.schemas import SafeExtraction
    from pydantic import ValidationError

    kwargs: dict[str, Any] = {}
    for k, v in merged.items():
        val = v.get("value")
        if val is None:
            continue
        if k == "document_date":
            coerced = _coerce_date_string(val)
            if coerced is None:
                merged[k]["confidence"] = 0.0
                logger.warning(
                    "document_date unparseable, dropping: %r", val
                )
                continue
            val = coerced
        kwargs[k] = val

    try:
        return SafeExtraction(**kwargs)
    except ValidationError as exc:
        bad_fields = set()
        for err in exc.errors():
            loc = err.get("loc", ())
            if loc:
                bad_fields.add(loc[0])
        logger.warning(
            "SafeExtraction validation failed; dropping %s",
            sorted(bad_fields),
        )
        for f in bad_fields:
            kwargs.pop(f, None)
            if f in merged:
                merged[f]["confidence"] = 0.0
        try:
            return SafeExtraction(**kwargs)
        except Exception as exc2:
            logger.warning("SafeExtraction failed after drop: %s", exc2)
            return None
    except Exception as exc:
        logger.warning("SafeExtraction unexpected error: %s", exc)
        return None


def _aggregate_confidence(
    per_field: dict[str, dict[str, Any]],
    critical: list[str],
    standard: list[str],
    optional: list[str],
) -> float:
    """Weighted mean over fields that are present in the source.

    Fields marked counts=False (source does not mention them) are
    excluded from both numerator and denominator. This is the correct
    semantic: an absent optional clause is not a miss.
    """
    def _num(fields: list[str], weight: float) -> float:
        total = 0.0
        for f in fields:
            entry = per_field.get(f, {})
            if not entry.get("counts", False):
                continue
            total += weight * float(entry.get("confidence", 0.0))
        return total

    def _den(fields: list[str], weight: float) -> float:
        total = 0.0
        for f in fields:
            entry = per_field.get(f, {})
            if not entry.get("counts", False):
                continue
            total += weight
        return total

    num = _num(critical, 1.0) + _num(standard, 0.6) + _num(optional, 0.3)
    den = _den(critical, 1.0) + _den(standard, 0.6) + _den(optional, 0.3)
    if den == 0:
        return 0.0
    return round(min(1.0, num / den), 3)
