"""Pydantic schemas for notifications and reminder logs."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.shared.enums import AttemptResultStatus, NotificationStatus, ReminderStage


class NotificationAttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    notification_id: uuid.UUID
    attempt_number: int
    started_at: datetime
    finished_at: datetime | None = None
    result_status: AttemptResultStatus
    telegram_message_id: int | None = None
    error_code: str | None = None
    error_summary: str | None = None


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rental_id: uuid.UUID
    customer_id: uuid.UUID
    reminder_stage: ReminderStage
    expiration_version: int
    scheduled_at: datetime
    status: NotificationStatus
    attempt_count: int
    sent_at: datetime | None = None
    telegram_message_id: int | None = None
    last_error: str | None = None
    customer_display_name: str | None = None
    customer_telegram_username: str | None = None
    product_name: str | None = None
    product_variant_name: str | None = None
    expiration_date: date | None = None
    attempts: list[NotificationAttemptRead] = []
    created_at: datetime
    updated_at: datetime
