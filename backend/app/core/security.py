"""Security utilities: password hashing, JWT tokens, and Telegram link token hashing."""

from datetime import timedelta
import hashlib
import secrets
from typing import Any

import bcrypt
import jwt

from app.core.config import settings
from app.shared.datetime_utils import utc_now


def hash_password(plain_password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plaintext password against its bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except ValueError:
        return False


def create_access_token(
    subject: str,
    roles: list[str] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token."""
    now = utc_now()
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: dict[str, Any] = {
        "sub": str(subject),
        "roles": roles or [],
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": "access",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token."""
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )


def generate_secure_token(nbytes: int = 32) -> tuple[str, str]:
    """Generate a cryptographically random URL-safe token and its SHA-256 hash.

    Returns:
        (raw_token, token_sha256_hash)
    """
    raw_token = secrets.token_urlsafe(nbytes)
    token_hash = hash_token(raw_token)
    return raw_token, token_hash


def hash_token(raw_token: str) -> str:
    """Compute SHA-256 hex digest of a token or idempotency payload."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
