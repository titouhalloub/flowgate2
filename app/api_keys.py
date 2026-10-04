"""Self-service API key generation, hashing, and verification.

Only the SHA-256 digest of a key is ever persisted. The plaintext is returned
once at creation and is unrecoverable thereafter.

Why SHA-256 and not bcrypt: keys carry 256 bits of entropy from
``secrets.token_urlsafe(32)``. They are not brute-forceable, so a password
KDF's cost factor would add latency on every authenticated request without
adding meaningful security -- material overhead when an MCP client fires
several tool calls in sequence. Verification uses a constant-time comparison.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

#: Recognised key prefixes. Anything starting with one of these is treated as a
#: database-backed key; everything else falls through to legacy env-var keys.
KEY_PREFIXES = ("fg_live_", "fg_test_")

#: Number of leading characters stored in plaintext so a user can identify a
#: key without exposing it.
PREFIX_LENGTH = 16

#: Roles assignable to a self-service key.
ALLOWED_ROLES = ("viewer", "reviewer", "compliance_officer", "admin")


def hash_api_key(plaintext: str) -> str:
    """Return the hex SHA-256 digest stored for ``plaintext``."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def generate_api_key(environment: str = "live") -> tuple[str, str, str]:
    """Mint a key. Returns ``(full_key, prefix, key_hash)``.

    ``full_key`` is returned to the caller exactly once and is never stored.
    """
    full_key = f"fg_{environment}_{secrets.token_urlsafe(32)}"
    prefix = full_key[:PREFIX_LENGTH]
    key_hash = hash_api_key(full_key)
    return full_key, prefix, key_hash


def verify_api_key(plaintext: str, key_hash: str) -> bool:
    """Constant-time check of ``plaintext`` against a stored digest."""
    candidate = hash_api_key(plaintext)
    return hmac.compare_digest(candidate, key_hash)


def is_managed_key(candidate: str) -> bool:
    """True when ``candidate`` looks like a database-backed key."""
    return candidate.startswith(KEY_PREFIXES)