from pydantic import ValidationError
import pytest

from app.core.config import Settings


def test_database_url_escapes_password_when_built_from_components() -> None:
    settings = Settings(
        _env_file=None,
        DATABASE_URL="",
        POSTGRES_USER="rental",
        POSTGRES_PASSWORD="pw@ss:/#",
        POSTGRES_HOST="db.internal",
        POSTGRES_PORT=5432,
        POSTGRES_DB="rentals",
    )

    assert settings.DATABASE_URL == (
        "postgresql+psycopg://rental:pw%40ss%3A%2F%23@db.internal:5432/rentals"
    )


def test_production_rejects_default_credentials_and_debug_mode() -> None:
    with pytest.raises(ValidationError, match="Unsafe production configuration"):
        Settings(_env_file=None, APP_ENV="production")


def test_production_accepts_explicit_non_default_secrets() -> None:
    settings = Settings(
        _env_file=None,
        APP_ENV="production",
        DEBUG=False,
        SECRET_KEY="s" * 48,
        INITIAL_OWNER_PASSWORD="non-default-initial-password",
        POSTGRES_PASSWORD="non-default-database-password",
        TELEGRAM_BOT_TOKEN="123456:valid-looking-token",
        TELEGRAM_ADMIN_USER_IDS=[987654321],
    )

    assert settings.APP_ENV == "production"
    assert settings.DEBUG is False
