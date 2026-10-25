"""Pydantic schemas for renewal offers and renewal requests."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import DurationUnit, RenewalModel, RenewalOfferStatus, RenewalStatus
from app.shared.money import DEFAULT_CURRENCY


class RenewalOfferCreate(BaseModel):
    rental_id: uuid.UUID
    offered_duration_value: int = Field(gt=0)
    offered_duration_unit: DurationUnit
    offered_price: Decimal = Field(ge=0)
    currency: str = DEFAULT_CURRENCY
    renewal_model: RenewalModel = RenewalModel.CONTINUOUS
    expires_in_hours: int = Field(default=72, gt=0, le=720)


class RenewalOfferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rental_id: uuid.UUID
    customer_id: uuid.UUID
    offered_duration_value: int
    offered_duration_unit: DurationUnit
    offered_price: Decimal
    currency: str
    renewal_model: RenewalModel
    status: RenewalOfferStatus
    expires_at: datetime
    selected_at: datetime | None = None
    created_at: datetime


class RenewalRequestCreate(BaseModel):
    duration_value: int = Field(gt=0)
    duration_unit: DurationUnit
    renewal_model: RenewalModel
    agreed_price: Decimal = Field(ge=0)
    currency: str = DEFAULT_CURRENCY
    confirmed_start_date: date | None = None


class RenewalApprovalRequest(BaseModel):
    renewal_model: RenewalModel
    confirmed_start_date: date | None = None


class RenewalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rental_id: uuid.UUID
    previous_start_date: date
    previous_expiration_date: date
    new_start_date: date
    new_expiration_date: date
    duration_value: int
    duration_unit: DurationUnit
    renewal_model: RenewalModel
    agreed_price: Decimal
    currency: str
    status: RenewalStatus
    created_by: uuid.UUID | None = None
    completed_at: datetime | None = None
    created_at: datetime
