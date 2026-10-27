"""Centralized configuration management using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

ROOT_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(ROOT_ENV_PATH), ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    APP_NAME: str = "Digital Product Rental Monitoring System"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"
    BUSINESS_TIMEZONE: str = "Asia/Jakarta"
    DEFAULT_CURRENCY: str = "IDR"

    SECRET_KEY: str = Field(
        default="dev-secret-key-for-local-development-only-at-least-32-chars",
        min_length=16,
    )
    CREDENTIALS_ENCRYPTION_KEY: str = (
        "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    INITIAL_OWNER_EMAIL: str = "owner@example.com"
    INITIAL_OWNER_PASSWORD: str = "ChangeMe123!"
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "rental_admin"
    POSTGRES_PASSWORD: str = "rental_secret_password"
    POSTGRES_DB: str = "rental_monitoring"
    DATABASE_URL: str = (
        "postgresql+psycopg://rental_admin:rental_secret_password@localhost:5432/rental_monitoring"
    )

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    TELEGRAM_BOT_TOKEN: str = "0000000000:AAExampleBotTokenReplaceBeforeRunningBot"
    TELEGRAM_ADMIN_USER_IDS: list[int] = [123456789]
    TELEGRAM_LINK_TOKEN_EXPIRE_MINUTES: int = 30

    DEFAULT_REMINDER_SEND_HOUR_WIB: int = 9
    DEFAULT_REMINDER_SEND_MINUTE_WIB: int = 0
    DEFAULT_OFFER_EXPIRE_HOURS: int = 72

    @model_validator(mode="after")
    def validate_runtime_configuration(self) -> "Settings":
        try:
            Fernet(self.CREDENTIALS_ENCRYPTION_KEY.encode("ascii"))
        except (UnicodeEncodeError, ValueError) as exc:
            raise ValueError(
                "CREDENTIALS_ENCRYPTION_KEY must be a URL-safe base64 Fernet key."
            ) from exc

        if not self.DATABASE_URL:
            self.DATABASE_URL = URL.create(
                "postgresql+psycopg",
                username=self.POSTGRES_USER,
                password=self.POSTGRES_PASSWORD,
                host=self.POSTGRES_HOST,
                port=self.POSTGRES_PORT,
                database=self.POSTGRES_DB,
            ).render_as_string(hide_password=False)

        if self.APP_ENV.lower() == "production":
            insecure_values = {
                "SECRET_KEY": self.SECRET_KEY
                == "dev-secret-key-for-local-development-only-at-least-32-chars",
                "INITIAL_OWNER_PASSWORD": self.INITIAL_OWNER_PASSWORD == "ChangeMe123!",
                "POSTGRES_PASSWORD": self.POSTGRES_PASSWORD == "rental_secret_password",
                "TELEGRAM_BOT_TOKEN": self.TELEGRAM_BOT_TOKEN
                == "0000000000:AAExampleBotTokenReplaceBeforeRunningBot",
                "TELEGRAM_ADMIN_USER_IDS": self.TELEGRAM_ADMIN_USER_IDS == [123456789],
                "CREDENTIALS_ENCRYPTION_KEY": self.CREDENTIALS_ENCRYPTION_KEY
                == "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
            }
            if self.DEBUG:
                insecure_values["DEBUG"] = True
            invalid = [name for name, is_insecure in insecure_values.items() if is_insecure]
            if invalid:
                raise ValueError(
                    "Unsafe production configuration; replace defaults for: "
                    + ", ".join(invalid)
                )
            if len(self.SECRET_KEY) < 32:
                raise ValueError("SECRET_KEY must be at least 32 characters in production.")
            if len(self.CREDENTIALS_ENCRYPTION_KEY) != 44:
                raise ValueError(
                    "CREDENTIALS_ENCRYPTION_KEY must be a URL-safe base64 Fernet key."
                )

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
