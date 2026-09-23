# Outbound webhook delivery service.
# Signature scheme (Stripe / GitHub style):
#   signature = HMAC-SHA256(secret, timestamp + "." + body)
#   headers: X-Flowgate-Signature: sha256=<hex>
#            X-Flowgate-Event, X-Flowgate-Delivery, X-Flowgate-Timestamp
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy.orm import Session

from app.models.orm import WebhookDelivery, WebhookSubscription

logger = logging.getLogger(__name__)

_DELIVERY_TIMEOUT_SECONDS = 5.0


def _sign(secret: str, timestamp: int, body: bytes) -> str:
    payload = f"{timestamp}.".encode("utf-8") + body
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _deliver_one(delivery: WebhookDelivery, subscription: WebhookSubscription) -> None:
    ts = int(time.time())
    body = json.dumps(delivery.payload, separators=(",", ":"), default=str).encode("utf-8")
    signature = _sign(subscription.secret, ts, body)

    headers = {
        "Content-Type": "application/json",
        "X-Flowgate-Signature": "sha256=" + signature,
        "X-Flowgate-Event": delivery.event_type,
        "X-Flowgate-Delivery": delivery.id,
        "X-Flowgate-Timestamp": str(ts),
        "User-Agent": "Flowgate-Webhooks/1.0",
    }

    delivery.attempts = (delivery.attempts or 0) + 1
    try:
        with httpx.Client(timeout=_DELIVERY_TIMEOUT_SECONDS) as client:
            r = client.post(subscription.url, content=body, headers=headers)
        delivery.response_status = r.status_code
        if 200 <= r.status_code < 300:
            delivery.status = "success"
            delivery.delivered_at = datetime.now(timezone.utc)
            delivery.last_error = None
        else:
            delivery.status = "failed"
            delivery.last_error = f"HTTP {r.status_code}: {r.text[:200]}"
    except Exception as exc:
        delivery.status = "failed"
        delivery.last_error = f"{type(exc).__name__}: {str(exc)[:200]}"


def fire_event(session: Session, event_type: str, payload: dict[str, Any]) -> int:
    # Deliver event_type to every active subscription that wants it.
    # Never raises; returns number of deliveries attempted.
    try:
        subs = (
            session.query(WebhookSubscription)
            .filter(WebhookSubscription.active.is_(True))
            .all()
        )
    except Exception as exc:
        logger.warning("webhook subscription lookup failed: %s", exc)
        return 0

    attempted = 0
    for sub in subs:
        if sub.events and event_type not in sub.events:
            continue
        delivery = WebhookDelivery(
            id="whd_" + uuid4().hex,
            subscription_id=sub.id,
            event_type=event_type,
            payload=payload,
            status="pending",
            attempts=0,
        )
        session.add(delivery)
        session.flush()
        _deliver_one(delivery, sub)
        attempted += 1

    if attempted:
        try:
            session.commit()
        except Exception as exc:
            logger.warning("webhook delivery commit failed: %s", exc)
            session.rollback()

    return attempted


def _enum_val(x: Any) -> str:
    if x is None:
        return ""
    return x.value if hasattr(x, "value") else str(x)


def fire_pipeline_webhooks(session: Session, instrument: Any, result: Any) -> None:
    # Fire document.processed or document.routed_to_review after a run.
    # Never raises.
    try:
        doc = getattr(result, "document", None)
        if doc is None:
            return
        routed = bool(getattr(result, "routed", False))
        event = "document.routed_to_review" if routed else "document.processed"

        payload = {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {
                "document_id": getattr(doc, "id", ""),
                "instrument_id": getattr(instrument, "id", ""),
                "issuer_name": getattr(instrument, "issuer_name", ""),
                "document_type": _enum_val(getattr(doc, "document_type", None)),
                "classification_confidence": getattr(doc, "classification_confidence", None),
                "extraction_confidence": getattr(doc, "extraction_confidence", None),
                "status": _enum_val(getattr(doc, "status", None)),
                "routed_to_review": routed,
                "outcome": _enum_val(getattr(result, "outcome", None)),
            },
        }
        fire_event(session, event, payload)
    except Exception as exc:
        logger.warning("fire_pipeline_webhooks failed: %s", exc)
