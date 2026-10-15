"""Password hashing (Argon2id) and JWT token helpers."""

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet
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


# ---- Room door access code encryption (FEAT-008) ----
# Codes are treated as strings so leading zeros are preserved.
#
# Key handling (remediation):
#   Primary key  : ACCESS_CODE_ENCRYPTION_KEY (Fernet), else derived from SECRET_KEY.
#   Legacy keys  : ACCESS_CODE_LEGACY_SECRETS (decrypt-only) + optionally SECRET_KEY.
#   Ciphertext   : optional "v<n>:" prefix; bare Fernet tokens are also accepted.
#   Rotation     : encrypt always uses primary; decrypt tries primary then legacies.
#                  Re-encrypt in place via reencrypt_access_code_token(); never log plaintext.

ACCESS_CODE_KEY_PREFIX_RE = re.compile(r"^v(\d+):(.+)$")

_fernet_by_material: dict[str, Fernet] = {}


def _fernet_from_material(material: str) -> Fernet:
    if material not in _fernet_by_material:
        import base64
        import hashlib

        # Accept a real Fernet key or derive one from arbitrary material.
        try:
            return _fernet_by_material.setdefault(material, Fernet(material.encode("ascii")))
        except Exception:
            digest = hashlib.sha256(material.encode("utf-8")).digest()
            _fernet_by_material[material] = Fernet(base64.urlsafe_b64encode(digest))
        return _fernet_by_material[material]
    return _fernet_by_material[material]


def _access_code_primary_material() -> str:
    dedicated = (settings.ACCESS_CODE_ENCRYPTION_KEY or "").strip()
    if dedicated:
        return dedicated
    # Backward-compatible fallback (pre-separation deployments)
    return settings.SECRET_KEY or "dev-only-insecure-secret"


def _access_code_legacy_materials() -> list[str]:
    """Decrypt-only materials. Order: explicit list, then JWT SECRET_KEY if requested."""
    out: list[str] = []
    raw = (settings.ACCESS_CODE_LEGACY_SECRETS or "").strip()
    if raw:
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            if part == "SECRET_KEY":
                out.append(settings.SECRET_KEY or "dev-only-insecure-secret")
            else:
                out.append(part)
    # Always try the JWT secret as a legacy source so pre-separation ciphertexts
    # keep working after switching to a dedicated key (unless it equals primary).
    secret = settings.SECRET_KEY or "dev-only-insecure-secret"
    if secret not in out and secret != _access_code_primary_material():
        out.append(secret)
    return out


def encrypt_access_code(plain: str) -> str:
    """Encrypt a room door access code. Input must already be a string.

    Output is "v2:<fernet-token>" so future key generations can migrate safely.
    """
    if not isinstance(plain, str):
        raise TypeError("access code must be a string to preserve leading zeros")
    token = _fernet_from_material(_access_code_primary_material()).encrypt(
        plain.encode("utf-8")
    ).decode("ascii")
    return f"v2:{token}"


def _split_access_code_token(token: str) -> tuple[str | None, str]:
    m = ACCESS_CODE_KEY_PREFIX_RE.match(token)
    if m:
        return f"v{m.group(1)}", m.group(2)
    return None, token


def decrypt_access_code(token: str) -> str:
    """Decrypt a room door access code. Tries primary key then legacy keys."""
    if not token:
        raise ValueError("empty access code token")
    _version, body = _split_access_code_token(token)
    errors: list[str] = []
    for material in [_access_code_primary_material(), *_access_code_legacy_materials()]:
        try:
            return _fernet_from_material(material).decrypt(body.encode("ascii")).decode("utf-8")
        except Exception as exc:  # noqa: BLE001 — try next key
            errors.append(type(exc).__name__)
    # Never include token body or plaintext in the error
    raise ValueError("access code cannot be decrypted with configured keys")


def reencrypt_access_code_token(token: str) -> str:
    """Re-encrypt an existing token under the current primary key.

    Safe for rotation. Returns the new "v2:..." token. Raises if undecryptable.
    """
    plain = decrypt_access_code(token)
    return encrypt_access_code(plain)


def access_code_needs_reencrypt(token: str | None) -> bool:
    if not token:
        return False
    version, _body = _split_access_code_token(token)
    # bare tokens and v1 (legacy) tokens should be rewritten to v2 primary
    return version != "v2"
