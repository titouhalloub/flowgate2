"""Authentication: API key OR Clerk JWT.

Two paths, one dependency. ``require_user`` accepts either:

    X-API-Key: <key>             programmatic (scripts, CI, webhooks)
    Authorization: Bearer <jwt>  UI users via Clerk

API keys come in two flavours:

* **Managed keys** -- ``fg_live_``/``fg_test_`` prefixed, minted per user via
  ``POST /api-keys``. Only a SHA-256 digest is stored; the row carries the
  role, optional expiry, and revocation state.
* **Legacy keys** -- whatever ``A27_API_KEYS`` holds, either as a flat
  comma-separated list (every entry is admin, the historical behaviour) or as
  a JSON object mapping key -> role.

Both paths return the same ``AuthUser``. The JWT path verifies against Clerk's
JWKS endpoint, upserts a row in ``users``, and returns the assigned role.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
    #: Issuer names this principal is scoped to. Stored and propagated but not
    #: yet enforced by any route -- see TECH-DEBT.md.
    scoped_issuers: list[str] | None = field(default=None)


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


def _api_keys() -> dict[str, str]:
    """Legacy env-var keys -> role.

    Accepts either the historical flat comma-separated list (every entry is
    ``admin``) or a JSON object mapping key -> role. The flat form preserves
    existing behaviour exactly; the JSON form is additive.
    """
    raw = (getattr(settings, "api_keys", "") or "").strip()
    if not raw:
        return {}
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.error("A27_API_KEYS is not valid JSON; refusing to authenticate")
            return {}
        if not isinstance(parsed, dict):
            logger.error("A27_API_KEYS JSON must be an object; refusing to authenticate")
            return {}
        return {str(k): str(v) for k, v in parsed.items()}
    return {k.strip(): "admin" for k in raw.split(",") if k.strip()}


def _authenticate_managed_key(
    plaintext: str, session: Session
) -> AuthUser | None:
    """Resolve a ``fg_live_``/``fg_test_`` key against the api_keys table.

    Returns ``None`` when the key is not managed; raises 401 for any managed
    key that is unknown, revoked, expired, or mismatched.
    """
    from app.api_keys import PREFIX_LENGTH, is_managed_key, verify_api_key
    from app.models.orm import ApiKey, User

    if not is_managed_key(plaintext):
        return None

    prefix = plaintext[:PREFIX_LENGTH]
    record = (
        session.query(ApiKey).filter(ApiKey.prefix == prefix).one_or_none()
    )
    if record is None:
        raise HTTPException(status_code=401, detail="Invalid API key.")
    if record.revoked_at is not None:
        raise HTTPException(status_code=401, detail="API key has been revoked.")
    now = datetime.now(timezone.utc)
    if record.expires_at is not None:
        expires = record.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < now:
            raise HTTPException(status_code=401, detail="API key has expired.")
    if not verify_api_key(plaintext, record.key_hash):
        raise HTTPException(status_code=401, detail="Invalid API key.")

    owner = session.query(User).filter(User.id == record.user_id).one_or_none()
    if owner is not None:
        try:
            record.last_used_at = now
            session.commit()
        except Exception:  # pragma: no cover - audit update is best effort
            session.rollback()
            logger.warning("Could not update last_used_at for API key")

    raw_scopes = record.scopes or {}
    issuers = raw_scopes.get("issuers") if isinstance(raw_scopes, dict) else None
    scoped = list(issuers) if isinstance(issuers, list) and issuers else None

    return AuthUser(
        id=record.user_id,
        email=owner.email if owner is not None else "api@flowgate.local",
        role=record.role,
        auth_method="api_key",
        external_auth_id=record.id,
        scoped_issuers=scoped,
    )


def require_user(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    session: Session = Depends(get_session),
) -> AuthUser:
    """Accept either an API key or a Clerk JWT. Fail closed."""

    keys = _api_keys()
    if not isinstance(keys, dict):  # tolerate a legacy list-shaped allowlist
        keys = {k: "admin" for k in keys}

    if x_api_key:
        managed = _authenticate_managed_key(x_api_key, session)
        if managed is not None:
            return managed
        if not keys:
            raise HTTPException(status_code=503, detail="Server authentication is not configured.")
        role = keys.get(x_api_key)
        if role is not None:
            return AuthUser(
                id="api_key",
                email="api@flowgate.local",
                role=role,
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
