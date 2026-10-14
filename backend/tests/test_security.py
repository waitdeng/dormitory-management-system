"""Security unit tests — no database required."""

from __future__ import annotations

import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token_value,
    decode_access_token,
    fingerprint_refresh_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    h = hash_password("Str0ng!Passw0rd")
    assert h != "Str0ng!Passw0rd"
    assert verify_password("Str0ng!Passw0rd", h)
    assert not verify_password("wrong-password", h)


def test_password_hash_is_argon2id():
    h = hash_password("Str0ng!Passw0rd")
    assert h.startswith("$argon2id$")


def test_access_token_roundtrip():
    token = create_access_token("42", username="alice", extra_claims={"roles": ["hr"]})
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["username"] == "alice"
    assert payload["type"] == "access"
    assert payload["roles"] == ["hr"]


def test_access_token_rejects_garbage():
    from app.core.exceptions import AuthenticationError

    with pytest.raises(AuthenticationError):
        decode_access_token("not.a.jwt")


def test_refresh_token_fingerprint_stable():
    from datetime import datetime

    raw, token_hash, expires_at = create_refresh_token_value()
    assert fingerprint_refresh_token(raw) == token_hash
    # expires_at is naive UTC and in the future
    assert expires_at.tzinfo is None
    assert expires_at > datetime.utcnow()
    # raw token must never equal its stored fingerprint
    assert raw != token_hash
