"""Password hashing (Argon2id) and JWT token helpers."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jwt import InvalidTokenError

from app.core.config import settings
from app.core.exceptions import AuthenticationError

_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a plaintext password with Argon2id."""
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against an Argon2id hash."""
    try:
        return _password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def create_access_token(
    subject: str,
    *,
    username: str,
    extra_claims: dict[str, Any] | None = None,
    expires_minutes: int | None = None,
) -> str:
    """Create a short-lived JWT access token."""
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": subject,
        "username": username,
        "type": "access",
        "jti": uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token_value() -> tuple[str, str, datetime]:
    """Return (raw_token, token_hash, expires_at). Only the hash is persisted.

    expires_at is naive UTC to match DATETIME(6) columns (see models.base.utcnow).
    """
    raw = uuid4().hex + uuid4().hex
    expires_at = (
        datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    ).replace(tzinfo=None)
    return raw, _token_fingerprint(raw), expires_at


def _token_fingerprint(raw_token: str) -> str:
    import hashlib

    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def fingerprint_refresh_token(raw_token: str) -> str:
    return _token_fingerprint(raw_token)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate an access JWT. Raises AuthenticationError on failure."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except InvalidTokenError as exc:
        raise AuthenticationError("Invalid or expired token") from exc
    if payload.get("type") != "access":
        raise AuthenticationError("Invalid token type")
    return payload
