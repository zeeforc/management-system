"""Pydantic schemas for authentication and administrator profile."""

from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None


class AdminUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    is_active: bool
    last_login_at: datetime | None = None
    roles: list[RoleRead] = []
    created_at: datetime
    updated_at: datetime
