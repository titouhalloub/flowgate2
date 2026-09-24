# Verifies webhook secrets are stored encrypted when the Fernet key is set,
# and that _decrypt_secret tolerates legacy plaintext.
from __future__ import annotations

from app import webhooks as wh


def test_decrypt_secret_plaintext_fallback():
    # A value that is not a Fernet token returns as-is. This is the
    # legacy path for rows written before encryption existed.
    assert wh._decrypt_secret("plain-secret") == "plain-secret"


def test_decrypt_secret_empty():
    assert wh._decrypt_secret("") == ""


def test_encrypt_then_sign_roundtrip(monkeypatch):
    # If the Fernet key is available, an encrypted secret must still
    # produce a valid HMAC signature. Signing uses the plaintext.
    from cryptography.fernet import Fernet
    from app.config import settings
    from app.security import encrypt_pii
    from app.webhooks import _sign, _decrypt_secret

    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "document_encryption_key", key)

    plain = "top-secret-for-test-16chars"
    encrypted = encrypt_pii(plain)
    assert encrypted != plain
    assert _decrypt_secret(encrypted) == plain

    sig = _sign(_decrypt_secret(encrypted), 1234, b"{}")
    expected = _sign(plain, 1234, b"{}")
    assert sig == expected
