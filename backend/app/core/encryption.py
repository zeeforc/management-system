"""Encryption helpers for sensitive account credentials stored in the database."""

from cryptography.fernet import Fernet

from app.core.config import settings


def encrypt_credential(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return Fernet(settings.CREDENTIALS_ENCRYPTION_KEY.encode("ascii")).encrypt(
        normalized.encode("utf-8")
    ).decode("ascii")


def decrypt_credential(value: str | None) -> str | None:
    if value is None:
        return None
    return Fernet(settings.CREDENTIALS_ENCRYPTION_KEY.encode("ascii")).decrypt(
        value.encode("ascii")
    ).decode("utf-8")
