"""Pydantic schemas for customers, notification consents, and Telegram linking."""

from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import ConsentStatus, ConsentType, CustomerStatus


class CustomerUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=160)
    telegram_username: str | None = Field(default=None, max_length=64)
    status: CustomerStatus | None = None
    internal_notes: str | None = None


class CustomerCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=160)
    telegram_username: str | None = Field(default=None, max_length=64)
    status: CustomerStatus = CustomerStatus.ACTIVE
    internal_notes: str | None = None


class CustomerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str
    telegram_username: str | None = None
    telegram_user_id: int | None = None
    telegram_chat_id: int | None = None
    status: CustomerStatus
    internal_notes: str | None = None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


class TelegramLinkTokenResponse(BaseModel):
    customer_id: uuid.UUID
    raw_token: str
    expires_at: datetime
    deep_link_command: str


class ConsentRecordRequest(BaseModel):
    consent_type: ConsentType = ConsentType.TELEGRAM_REMINDERS
    consent_status: ConsentStatus = ConsentStatus.GRANTED
    source: str = Field(default="ADMIN_DASHBOARD", max_length=64)


class ConsentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    consent_type: ConsentType
    consent_status: ConsentStatus
    source: str
    consented_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime
