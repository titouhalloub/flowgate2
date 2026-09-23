"""Tests for app/auth.py."""

from __future__ import annotations
from unittest.mock import MagicMock
import pytest
from app import auth as auth_module


def test_rejects_missing_credentials(monkeypatch):
    monkeypatch.setattr(auth_module, "_api_keys", lambda: ["valid_key"])
    with pytest.raises(Exception) as exc:
        auth_module.require_user(request=MagicMock(), x_api_key=None, authorization=None, session=MagicMock())
    assert "Authentication required" in str(exc.value) or "401" in str(exc.value)


def test_rejects_wrong_api_key(monkeypatch):
    monkeypatch.setattr(auth_module, "_api_keys", lambda: ["valid_key"])
    with pytest.raises(Exception) as exc:
        auth_module.require_user(request=MagicMock(), x_api_key="wrong", authorization=None, session=MagicMock())
    assert "Invalid API key" in str(exc.value) or "401" in str(exc.value)


def test_accepts_valid_api_key(monkeypatch):
    monkeypatch.setattr(auth_module, "_api_keys", lambda: ["valid_key"])
    user = auth_module.require_user(request=MagicMock(), x_api_key="valid_key", authorization=None, session=MagicMock())
    assert user.role == "admin"
    assert user.auth_method == "api_key"


def test_fails_closed_on_empty_allowlist(monkeypatch):
    monkeypatch.setattr(auth_module, "_api_keys", lambda: [])
    with pytest.raises(Exception) as exc:
        auth_module.require_user(request=MagicMock(), x_api_key="any", authorization=None, session=MagicMock())
    assert "503" in str(exc.value) or "not configured" in str(exc.value)


def test_rejects_invalid_jwt(monkeypatch):
    monkeypatch.setattr(auth_module, "_api_keys", lambda: ["valid_key"])
    monkeypatch.setattr(auth_module, "verify_clerk_jwt", lambda t: None)
    with pytest.raises(Exception) as exc:
        auth_module.require_user(request=MagicMock(), x_api_key=None, authorization="Bearer x.y.z", session=MagicMock())
    assert "Invalid" in str(exc.value) or "401" in str(exc.value)


def test_accepts_valid_jwt(monkeypatch):
    monkeypatch.setattr(auth_module, "_api_keys", lambda: ["valid_key"])
    monkeypatch.setattr(auth_module, "verify_clerk_jwt", lambda t: {"sub": "u1", "email": "a@b.com"})
    fake = MagicMock(); fake.id = "1"; fake.email = "a@b.com"; fake.role = "viewer"
    monkeypatch.setattr(auth_module, "_upsert_clerk_user", lambda s, i, c: fake)
    user = auth_module.require_user(request=MagicMock(), x_api_key=None, authorization="Bearer x.y.z", session=MagicMock())
    assert user.role == "viewer"
    assert user.auth_method == "clerk"


def test_require_role_rejects_wrong_role(monkeypatch):
    fake = auth_module.AuthUser(id="x", email="e", role="viewer", auth_method="clerk", external_auth_id="x")
    dep = auth_module.require_role("compliance_officer")
    with pytest.raises(Exception) as exc:
        dep(user=fake)
    assert "403" in str(exc.value) or "Requires" in str(exc.value)


def test_require_role_allows_admin():
    fake = auth_module.AuthUser(id="x", email="e", role="admin", auth_method="api_key", external_auth_id="api_key")
    dep = auth_module.require_role("compliance_officer")
    assert dep(user=fake) is fake
