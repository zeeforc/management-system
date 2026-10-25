"""Pydantic schemas for manual payments and verification."""

from datetime import datetime
from decimal import Decimal
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import PaymentMethod, PaymentStatus
from app.shared.money import DEFAULT_CURRENCY


class PaymentCreate(BaseModel):
    customer_id: uuid.UUID
    rental_id: uuid.UUID
    renewal_id: uuid.UUID | None = None
    amount: Decimal = Field(gt=0)
    currency: str = DEFAULT_CURRENCY
    payment_method: PaymentMethod = PaymentMethod.BANK_TRANSFER
    payment_reference: str | None = Field(default=None, max_length=128)
    paid_at: datetime | None = None


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    rental_id: uuid.UUID
    renewal_id: uuid.UUID | None = None
    amount: Decimal
    currency: str
    payment_method: PaymentMethod
    status: PaymentStatus
    payment_reference: str | None = None
    paid_at: datetime | None = None
    verified_at: datetime | None = None
    verified_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
