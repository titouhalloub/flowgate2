"""LLM-based extraction with verifier (Phase E3).

Generic across every document type registered in EXTRACTION_ROUTE_NAMES.
The per-type differences are:
  - which pydantic schema validates the result (resolved via the registry)
  - optional confidence weights (fields default to 1.0 when unlisted)

The pipeline is always:
  1. _call_extract  -> per-field {value, evidence, confidence}
  2. _call_verify   -> per-field {present_in_source, supported, confidence}
  3. _merge         -> {value, confidence, counts}
  4. _instantiate   -> pydantic instance (dates coerced, bad fields dropped)
  5. _aggregate     -> single float in [0.0, 1.0]

The classifier remains advisory: the caller passes document_type to
extract_with_llm, which routes the request into whichever schema is
registered for that type.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from app.config import settings

if TYPE_CHECKING:
    from app.extraction import ExtractionOutcome

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Confidence weights (only SAFE has explicit tuning so far).
# Fields not listed default to weight 1.0 in the aggregate.
# ---------------------------------------------------------------------------
_EXPLICIT_WEIGHTS: dict[str, dict[str, list[str]]] = {
    "safe": {
        "critical": [
            "company_name", "purchase_amount", "valuation_cap", "currency",
        ],
        "standard": [
            "investor_name", "instrument_kind", "discount_rate",
        ],
        "optional": [
            "pro_rata_rights", "mfn_clause",
            "conversion_trigger", "document_date",
        ],
    },
}

_META_FIELDS = {"schema_name", "schema_version", "extracted_at", "source_text"}


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

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


def _call_with_retry(fn, *, attempts: int = 3, base_delay: float = 1.5):
    """Retry an LLM call on transient failures (503, empty choices, etc.)."""
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("LLM attempt %d/%d failed: %s", i + 1, attempts, exc)
            if i < attempts - 1:
                time.sleep(base_delay * (2 ** i))
    assert last_exc is not None
    raise last_exc


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def extract_with_llm(text: str, document_type: str) -> "ExtractionOutcome | None":
    """Try LLM extraction for any registered document type.
    Return None on any failure so the regex extractor runs unchanged."""
    schema_name, schema_class = _resolve_schema(document_type)
    if schema_class is None:
        return None

    resolved = _get_client()
    if resolved is None:
        return None
    client, model = resolved

    logger.info("LLM extract using model=%s schema=%s", model, schema_name)

    try:
        extracted = _call_with_retry(
            lambda: _call_extract(client, model, text, schema_class)
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("LLM extract failed after retries: %s", exc)
        return None
    if not extracted:
        logger.warning("LLM extract returned empty dict")
        return None

    try:
        verified = _call_with_retry(
            lambda: _call_verify(client, model, text, extracted),
            attempts=2,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM verify failed after retries, degrading: %s", exc)
        verified = {}

    try:
        merged = _merge(extracted, verified)
    except Exception as exc:  # noqa: BLE001
        logger.exception("LLM merge raised: %s", exc)
        return None

    try:
        instance = _instantiate(schema_class, merged)
    except Exception as exc:  # noqa: BLE001
        logger.exception("LLM instantiate raised: %s", exc)
        return None
    if instance is None:
        return None

    weights = _EXPLICIT_WEIGHTS.get(document_type, {})
    try:
        confidence = _aggregate_confidence(
            merged,
            weights.get("critical", []),
            weights.get("standard", []),
            weights.get("optional", []),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("LLM aggregate raised: %s", exc)
        return None

    from app.extraction import ExtractionOutcome

    try:
        return ExtractionOutcome(
            schema_name=schema_name,
            schema_version="v1",
            extraction=instance,
            confidence=confidence,
            routed_to_review=confidence < settings.extraction_llm_min_confidence,
            extracted_data={"data": instance.model_dump(mode="json")},
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("LLM outcome construct raised: %s", exc)
        return None


def _resolve_schema(document_type: str) -> tuple[str | None, type | None]:
    """Map a document_type string to (schema_name, pydantic_class)."""
    try:
        from app.extraction import EXTRACTION_ROUTE_NAMES
        from app.models.enums import DocumentType
        from app import schemas as schemas_module
    except Exception as exc:  # noqa: BLE001
        logger.warning("schema resolution import failed: %s", exc)
        return None, None

    try:
        doc_enum = DocumentType(document_type)
    except ValueError:
        return None, None

    schema_name = EXTRACTION_ROUTE_NAMES.get(doc_enum)
    if schema_name is None:
        return None, None

    schema_class = getattr(schemas_module, schema_name, None)
    if schema_class is None:
        return None, None

    return schema_name, schema_class


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

def _call_extract(client: Any, model: str, text: str, schema_class: type) -> dict[str, Any] | None:
    schema_name = schema_class.__name__
    docstring = (schema_class.__doc__ or "").strip()
    schema = schema_class.model_json_schema()
    properties = schema.get("properties", {})
    field_list = [f for f in properties if f not in _META_FIELDS]

    system = (
        f"You extract structured data from private-capital documents "
        f"into the {schema_name} schema.\n\n"
        f"Schema description:\n{docstring}\n\n"
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
        raise RuntimeError("extract: OpenRouter returned None")
    choices = getattr(resp, "choices", None)
    if not choices:
        err = getattr(resp, "error", None)
        raise RuntimeError(f"extract: no choices in response: {err!r}")
    msg = getattr(choices[0], "message", None)
    if msg is None:
        raise RuntimeError("extract: choices[0].message is None")
    content = getattr(msg, "content", None)
    if not content:
        raise RuntimeError("extract: message.content is empty")
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


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------

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
        "about this field. Set supported=false, confidence 0.0 in that case.\n"
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
        raise RuntimeError("verify: OpenRouter returned None")
    choices = getattr(resp, "choices", None)
    if not choices:
        err = getattr(resp, "error", None)
        raise RuntimeError(f"verify: no choices in response: {err!r}")
    msg = getattr(choices[0], "message", None)
    if msg is None:
        raise RuntimeError("verify: choices[0].message is None")
    content = getattr(msg, "content", None)
    if not content:
        raise RuntimeError("verify: message.content is empty")
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


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

def _merge(
    extracted: dict[str, Any],
    verified: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Combine extract + verify.

    Each merged entry carries a `counts` flag:
      - counts=False: field not present in the source; excluded from
        the aggregate.
      - counts=True: field present in the source; its confidence
        contributes to the aggregate.

    If verify returned {} (transient API failure), fall back to trusting
    extract's own confidence for non-null values.
    """
    merged: dict[str, dict[str, Any]] = {}
    verify_failed = not verified

    for field, e in extracted.items():
        if not isinstance(e, dict):
            continue

        if verify_failed:
            val = e.get("value")
            if val is None:
                merged[field] = {"value": None, "confidence": 0.0, "counts": False}
            else:
                try:
                    conf = float(e.get("confidence", 0.0))
                except (TypeError, ValueError):
                    conf = 0.0
                merged[field] = {"value": val, "confidence": conf, "counts": True}
            continue

        v = verified.get(field, {})
        if not isinstance(v, dict):
            v = {}

        present = bool(v.get("present_in_source", False))
        supported = bool(v.get("supported", False))

        if not present:
            merged[field] = {"value": None, "confidence": 0.0, "counts": False}
            continue

        if not supported or e.get("value") is None:
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


# ---------------------------------------------------------------------------
# Instantiate
# ---------------------------------------------------------------------------

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


def _instantiate(schema_class: type, merged: dict[str, dict[str, Any]]):
    """Build a pydantic instance from merged fields.

    Coerces date strings; drops fields pydantic rejects rather than
    abandoning the whole extraction. Mutates merged in place so the
    aggregate reflects any drops.
    """
    from pydantic import ValidationError

    date_fields = {
        name for name, f in schema_class.model_fields.items()
        if "date" in str(f.annotation).lower()
        or (hasattr(f.annotation, "__name__") and "date" in f.annotation.__name__.lower())
    }

    kwargs: dict[str, Any] = {}
    for k, v in merged.items():
        if k in _META_FIELDS:
            continue
        if k not in schema_class.model_fields:
            continue
        val = v.get("value")
        if val is None:
            continue
        if k in date_fields:
            coerced = _coerce_date_string(val)
            if coerced is None:
                merged[k]["confidence"] = 0.0
                logger.warning("date field %s unparseable, dropping: %r", k, val)
                continue
            val = coerced
        kwargs[k] = val

    try:
        return schema_class(**kwargs)
    except ValidationError as exc:
        bad_fields: set[str] = set()
        for err in exc.errors():
            loc = err.get("loc", ())
            if loc:
                bad_fields.add(str(loc[0]))
        logger.warning(
            "instantiate %s failed; dropping %s",
            schema_class.__name__, sorted(bad_fields),
        )
        for f in bad_fields:
            kwargs.pop(f, None)
            if f in merged:
                merged[f]["confidence"] = 0.0
        try:
            return schema_class(**kwargs)
        except Exception as exc2:  # noqa: BLE001
            logger.warning("instantiate retry failed: %s", exc2)
            return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("instantiate unexpected error: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

def _aggregate_confidence(
    per_field: dict[str, dict[str, Any]],
    critical: list[str],
    standard: list[str],
    optional: list[str],
) -> float:
    """Weighted mean over fields that are present in the source.

    Fields in `critical` get weight 1.0, `standard` 0.6, `optional` 0.3.
    Fields not listed in any group default to weight 1.0.
    Fields marked counts=False are excluded entirely.
    """
    field_weights: dict[str, float] = {}
    for f in critical:
        field_weights[f] = 1.0
    for f in standard:
        field_weights[f] = 0.6
    for f in optional:
        field_weights[f] = 0.3

    num = 0.0
    den = 0.0
    for field, entry in per_field.items():
        if not isinstance(entry, dict):
            continue
        if not entry.get("counts", False):
            continue
        try:
            c = float(entry.get("confidence", 0.0))
        except (TypeError, ValueError):
            c = 0.0
        w = field_weights.get(field, 1.0)
        num += w * c
        den += w

    if den == 0:
        return 0.0
    return round(min(1.0, num / den), 3)
