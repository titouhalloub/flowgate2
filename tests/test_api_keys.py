"""API key minting, hashing, scoping, revocation, and legacy compatibility."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api_keys import generate_api_key, verify_api_key
from app.auth import AuthUser, require_user
from app.db import Base, get_session
from app.main import app
from app.models.orm import ApiKey, User

LEGACY_KEY = "development_key_123"

#: The identity the AuthUser override presents. A seeded users row must use this
#: id, otherwise api_keys.user_id violates the FK.
DEFAULT_OWNER = "admin-1"


def _admin(user_id=DEFAULT_OWNER, role="admin"):
    return AuthUser(
        id=user_id,
        email="admin@example.com",
        role=role,
        auth_method="clerk",
        external_auth_id=user_id,
    )


@pytest.fixture()
def key_client(tmp_path):
    """Real auth path (require_user NOT overridden) over a scratch DB."""
    engine = create_engine(f"sqlite:///{tmp_path / 'keys.db'}", future=True)
    Base.metadata.create_all(engine)
    Local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _override_get_session():
        with Local() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    try:
        yield TestClient(app), Local
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def _seed_owner(Local, user_id=DEFAULT_OWNER):
    s = Local()
    s.add(User(id=user_id, external_auth_id=f"ext_{user_id}", email="o@e.com", role="admin"))
    s.commit()
    s.close()


def _mint(Local, user_id=DEFAULT_OWNER, role="viewer", **kw):
    full, prefix, key_hash = generate_api_key()
    s = Local()
    rec = ApiKey(
        id=f"k_{prefix}",
        user_id=user_id,
        name=kw.pop("name", "Test"),
        prefix=prefix,
        key_hash=key_hash,
        role=role,
        scopes=kw.pop("scopes", {}),
        expires_at=kw.pop("expires_at", None),
    )
    s.add(rec)
    s.commit()
    s.close()
    return full, rec.id


# --- pure helpers -------------------------------------------------------

def test_generate_and_verify():
    full, prefix, key_hash = generate_api_key()
    assert full.startswith("fg_live_")
    assert prefix == full[:16]
    assert verify_api_key(full, key_hash) is True
    assert verify_api_key(full + "tamper", key_hash) is False


def test_prefix_uniqueness():
    seen = {generate_api_key()[1] for _ in range(50)}
    assert len(seen) == 50


# --- HTTP behaviour -----------------------------------------------------

def test_create_returns_plaintext_once(key_client):
    client, Local = key_client
    _seed_owner(Local)
    with client:
        app.dependency_overrides[require_user] = lambda: _admin()
        created = client.post("/api-keys", json={"name": "CI", "role": "viewer"})
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["key"].startswith("fg_live_")
        assert body["prefix"] == body["key"][:16]
        listed = client.get("/api-keys")
        app.dependency_overrides.pop(require_user, None)
    assert listed.status_code == 200
    row = listed.json()[0]
    assert "key" not in row
    assert "key_hash" not in row
    assert row["prefix"] == body["prefix"]


def test_get_never_exposes_secret(key_client):
    client, Local = key_client
    _seed_owner(Local)
    _mint(Local)
    with client:
        app.dependency_overrides[require_user] = lambda: _admin()
        r = client.get("/api-keys")
        app.dependency_overrides.pop(require_user, None)
    assert r.status_code == 200
    assert "key_hash" not in r.text


def test_new_key_works(key_client):
    client, Local = key_client
    _seed_owner(Local)
    full, _ = _mint(Local, role="viewer")
    r = client.get("/issuers", headers={"X-API-Key": full})
    assert r.status_code == 200, r.text


def test_revoked_key_rejected(key_client):
    client, Local = key_client
    _seed_owner(Local)
    full, rec_id = _mint(Local, role="viewer")
    assert client.get("/issuers", headers={"X-API-Key": full}).status_code == 200
    with client:
        app.dependency_overrides[require_user] = lambda: _admin()
        d = client.delete(f"/api-keys/{rec_id}")
        app.dependency_overrides.pop(require_user, None)
    assert d.status_code == 200, d.text
    assert client.get("/issuers", headers={"X-API-Key": full}).status_code == 401


def test_expired_key_rejected(key_client):
    client, Local = key_client
    _seed_owner(Local)
    past = datetime.now(timezone.utc) - timedelta(days=1)
    full, _ = _mint(Local, role="viewer", expires_at=past)
    assert client.get("/issuers", headers={"X-API-Key": full}).status_code == 401


def test_legacy_key_still_works(key_client):
    client, _ = key_client
    r = client.get("/issuers", headers={"X-API-Key": LEGACY_KEY})
    assert r.status_code == 200, r.text


def test_max_keys_per_user(key_client):
    client, Local = key_client
    _seed_owner(Local)
    with client:
        app.dependency_overrides[require_user] = lambda: _admin()
        for i in range(10):
            r = client.post("/api-keys", json={"name": f"k{i}", "role": "viewer"})
            assert r.status_code == 201, r.text
        eleventh = client.post("/api-keys", json={"name": "k10", "role": "viewer"})
        app.dependency_overrides.pop(require_user, None)
    assert eleventh.status_code in (400, 429)


def test_invalid_role_rejected(key_client):
    client, Local = key_client
    _seed_owner(Local)
    with client:
        app.dependency_overrides[require_user] = lambda: _admin()
        r = client.post("/api-keys", json={"name": "bad", "role": "superuser"})
        app.dependency_overrides.pop(require_user, None)
    assert r.status_code == 400


def test_scopes_attached_not_enforced(key_client):
    client, Local = key_client
    _seed_owner(Local)
    full, _ = _mint(Local, role="viewer", scopes={"issuers": ["Flowgate Systems Inc."]})
    assert client.get("/issuers", headers={"X-API-Key": full}).status_code == 200


def test_revoke_is_idempotent(key_client):
    client, Local = key_client
    _seed_owner(Local)
    _, rec_id = _mint(Local)
    with client:
        app.dependency_overrides[require_user] = lambda: _admin()
        a = client.delete(f"/api-keys/{rec_id}")
        b = client.delete(f"/api-keys/{rec_id}")
        app.dependency_overrides.pop(require_user, None)
    assert a.status_code == 200 and b.status_code == 200


def test_cannot_revoke_other_users_key(key_client):
    client, Local = key_client
    _seed_owner(Local)
    _, rec_id = _mint(Local, user_id=DEFAULT_OWNER)
    with client:
        app.dependency_overrides[require_user] = lambda: _admin("intruder-1", role="viewer")
        r = client.delete(f"/api-keys/{rec_id}")
        app.dependency_overrides.pop(require_user, None)
    assert r.status_code == 403