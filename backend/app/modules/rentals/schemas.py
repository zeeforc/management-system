"""Pydantic schemas for rental creation and derived status presentation."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import (
    DurationUnit,
    ExpirationWarningState,
    RenewalModel,
    RentalStatus,
)
from app.shared.money import DEFAULT_CURRENCY


class RentalUpdate(BaseModel):
    customer_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    product_variant_id: uuid.UUID | None = None
    start_date: date | None = None
    expiration_date: date | None = None
    duration_value: int | None = Field(default=None, gt=0)
    duration_unit: DurationUnit | None = None
    agreed_price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = None
    status: RentalStatus | None = None
    renewal_model: RenewalModel | None = None


class RentalCreate(BaseModel):
    customer_id: uuid.UUID
    product_id: uuid.UUID
    product_variant_id: uuid.UUID
    start_date: date
    expiration_date: date | None = None
    duration_value: int | None = Field(default=None, gt=0)
    duration_unit: DurationUnit | None = None
    agreed_price: Decimal | None = Field(default=None, ge=0)
    currency: str = DEFAULT_CURRENCY
    renewal_model: RenewalModel = RenewalModel.CONTINUOUS


class RentalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    product_id: uuid.UUID
    product_variant_id: uuid.UUID
    start_date: date
    expiration_date: date
    expiration_version: int
    duration_value: int
    duration_unit: DurationUnit
    agreed_price: Decimal
    currency: str
    status: RentalStatus
    effective_status: RentalStatus
    warning_state: ExpirationWarningState
    days_remaining: int
    renewal_model: RenewalModel
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
