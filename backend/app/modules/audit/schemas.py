"""Pydantic schemas for audit logs and system settings."""

from datetime import datetime
from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict

from app.shared.enums import ActorType


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_type: ActorType
    actor_id: str | None = None
    action: str
    entity_type: str
    entity_id: str
    before_data: dict[str, Any] | None = None
    after_data: dict[str, Any] | None = None
    request_id: str | None = None
    created_at: datetime


class SystemSettingUpsert(BaseModel):
    value: dict[str, Any]


class SystemSettingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    value: dict[str, Any]
    updated_by: uuid.UUID | None = None
    updated_at: datetime
