# Webhook subscription and delivery management routes.
from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import logging

from app.api_schemas import (
    WebhookDeliveryOut,
    WebhookSubscriptionCreate,
    WebhookSubscriptionOut,
)
from app.auth import require_user as require_api_key
from app.db import get_session
from app.models.orm import WebhookDelivery, WebhookSubscription

logger = logging.getLogger(__name__)


def _encrypt_secret(plain: str) -> str:
    """Encrypt a webhook secret with the shared Fernet key.

    Falls back to plaintext (with a warning) when
    A27_DOCUMENT_ENCRYPTION_KEY is unset -- the webhook layer stays
    usable in a demo deployment, but operators get a clear signal.
    """
    try:
        from app.security import encrypt_pii
        return encrypt_pii(plain)
    except Exception as exc:
        logger.warning(
            "webhook secret stored in plaintext: %s "
            "(set A27_DOCUMENT_ENCRYPTION_KEY to encrypt at rest)",
            exc,
        )
        return plain

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("", response_model=WebhookSubscriptionOut, status_code=201)
def create_webhook_subscription(
    payload: WebhookSubscriptionCreate,
    session: Session = Depends(get_session),
    _: Any = Depends(require_api_key),
) -> WebhookSubscription:
    sub = WebhookSubscription(
        id="whs_" + uuid4().hex,
        url=payload.url,
        secret=_encrypt_secret(payload.secret),
        events=list(payload.events or []),
        description=payload.description,
        active=True,
        created_by=payload.created_by,
    )
    session.add(sub)
    session.commit()
    session.refresh(sub)
    return sub


@router.get("", response_model=list[WebhookSubscriptionOut])
def list_webhook_subscriptions(
    session: Session = Depends(get_session),
    _: Any = Depends(require_api_key),
) -> list[WebhookSubscription]:
    return (
        session.query(WebhookSubscription)
        .order_by(WebhookSubscription.created_at.desc())
        .all()
    )


@router.delete("/{subscription_id}", status_code=204)
def delete_webhook_subscription(
    subscription_id: str,
    session: Session = Depends(get_session),
    _: Any = Depends(require_api_key),
) -> None:
    sub = session.get(WebhookSubscription, subscription_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    sub.active = False
    session.commit()


@router.get("/{subscription_id}/deliveries", response_model=list[WebhookDeliveryOut])
def list_deliveries(
    subscription_id: str,
    limit: int = Query(default=20, ge=1, le=200),
    session: Session = Depends(get_session),
    _: Any = Depends(require_api_key),
) -> list[WebhookDelivery]:
    return (
        session.query(WebhookDelivery)
        .filter(WebhookDelivery.subscription_id == subscription_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(limit)
        .all()
    )


@router.post("/{subscription_id}/test")
def send_test_event(
    subscription_id: str,
    session: Session = Depends(get_session),
    _: Any = Depends(require_api_key),
) -> dict[str, Any]:
    from datetime import datetime, timezone
    from app.webhooks import _deliver_one

    sub = session.get(WebhookSubscription, subscription_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="Subscription not found")

    payload = {
        "event": "webhook.test",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {"message": "Flowgate webhook test event"},
    }
    delivery = WebhookDelivery(
        id="whd_" + uuid4().hex,
        subscription_id=sub.id,
        event_type="webhook.test",
        payload=payload,
        status="pending",
        attempts=0,
    )
    session.add(delivery)
    session.flush()
    _deliver_one(delivery, sub)
    session.commit()
    return {
        "delivery_id": delivery.id,
        "status": delivery.status,
        "response_status": delivery.response_status,
        "last_error": delivery.last_error,
    }


@router.post("/deliveries/{delivery_id}/retry")
def retry_delivery(
    delivery_id: str,
    session: Session = Depends(get_session),
    _: Any = Depends(require_api_key),
) -> dict[str, Any]:
    from app.webhooks import _deliver_one

    delivery = session.get(WebhookDelivery, delivery_id)
    if delivery is None:
        raise HTTPException(status_code=404, detail="Delivery not found")
    sub = session.get(WebhookSubscription, delivery.subscription_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="Subscription not found")

    delivery.status = "pending"
    _deliver_one(delivery, sub)
    session.commit()
    return {
        "delivery_id": delivery.id,
        "status": delivery.status,
        "response_status": delivery.response_status,
        "last_error": delivery.last_error,
    }
