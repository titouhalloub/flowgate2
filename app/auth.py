"""Authentication: API key OR Clerk JWT.

Two paths, one dependency. ``require_user`` accepts either:

    X-API-Key: <key>             programmatic (scripts, CI, webhooks)
    Authorization: Bearer <jwt>  UI users via Clerk

The API key path maps to a synthetic admin identity. The JWT path
verifies against Clerk's JWKS endpoint, upserts a row in ``users``,
and returns the assigned role.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session

logger = logging.getLogger(__name__)


@dataclass
class AuthUser:
    id: str
    email: str
    role: str
    auth_method: str
    external_auth_id: str


_jwks_client: Any = None


def _get_jwks_client():
    global _jwks_client
    if _jwks_client is not None:
        return _jwks_client
    if not settings.clerk_jwks_url:
        return None
    try:
        from jwt import PyJWKClient
    except ImportError:
        logger.warning("pyjwt not installed; Clerk path disabled")
        return None
    _jwks_client = PyJWKClient(settings.clerk_jwks_url, cache_keys=True)
    return _jwks_client


def verify_clerk_jwt(token: str) -> dict[str, Any] | None:
    import jwt as pyjwt

    client = _get_jwks_client()
    if client is None:
        return None
    try:
        signing_key = client.get_signing_key_from_jwt(token)
        kwargs: dict[str, Any] = {"algorithms": ["RS256"], "options": {"verify_aud": False}}
        if settings.clerk_issuer:
            kwargs["issuer"] = settings.clerk_issuer
        return pyjwt.decode(token, signing_key.key, **kwargs)
    except Exception as exc:
        logger.info("JWT verification failed: %s", exc)
        return None


def _upsert_clerk_user(session: Session, external_id: str, claims: dict) -> Any:
    from datetime import datetime, timezone
    from uuid import uuid4
    from app.models.orm import User

    try:
        user = session.query(User).filter(User.external_auth_id == external_id).one_or_none()
        email = claims.get("email") or claims.get("primary_email_address") or ""
        if user is None:
            user = User(
                id=str(uuid4()),
                external_auth_id=external_id,
                email=email,
                name=claims.get("name"),
                role="viewer",
            )
            session.add(user)
        user.last_login_at = datetime.now(timezone.utc)
        session.flush()
        return user
    except Exception as exc:
        logger.warning("User upsert failed: %s", exc)
        session.rollback()
        return None


def _api_keys() -> list[str]:
    raw = getattr(settings, "api_keys", "") or ""
    return [k.strip() for k in raw.split(",") if k.strip()]


def require_user(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    session: Session = Depends(get_session),
) -> AuthUser:
    """Accept either an API key or a Clerk JWT. Fail closed."""

    keys = _api_keys()
    if not keys:
        raise HTTPException(status_code=503, detail="Server authentication is not configured.")

    if x_api_key:
        if x_api_key in keys:
            return AuthUser(
                id="api_key",
                email="api@flowgate.local",
                role="admin",
                auth_method="api_key",
                external_auth_id="api_key",
            )
        raise HTTPException(status_code=401, detail="Invalid API key.")

    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        claims = verify_clerk_jwt(token)
        if claims is None:
            raise HTTPException(status_code=401, detail="Invalid or expired token.")
        sub = claims.get("sub")
        if not sub:
            raise HTTPException(status_code=401, detail="Token missing subject claim.")
        user = _upsert_clerk_user(session, sub, claims)
        if user is None:
            return AuthUser(
                id=sub, email=claims.get("email") or "", role="viewer",
                auth_method="clerk", external_auth_id=sub,
            )
        return AuthUser(
            id=user.id, email=user.email, role=user.role,
            auth_method="clerk", external_auth_id=sub,
        )

    raise HTTPException(
        status_code=401,
        detail="Authentication required: provide X-API-Key or Authorization: Bearer <jwt>.",
    )


require_api_key = require_user


def require_role(*allowed: str):
    def _dep(user: AuthUser = Depends(require_user)) -> AuthUser:
        if user.role not in allowed and user.role != "admin":
            raise HTTPException(status_code=403, detail=f"Requires one of: {', '.join(allowed)}")
        return user
    return _dep
