"""Pydantic schemas for products and product variants."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import DurationUnit, ProductStatus, VariantStatus
from app.shared.money import DEFAULT_CURRENCY


class ProductVariantCreate(BaseModel):
    product_id: uuid.UUID
    name: str = Field(min_length=1, max_length=160)
    duration_value: int = Field(gt=0)
    duration_unit: DurationUnit
    default_price: Decimal = Field(ge=0)
    currency: str = DEFAULT_CURRENCY
    status: VariantStatus = VariantStatus.ACTIVE


class ProductVariantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    name: str
    duration_value: int
    duration_unit: DurationUnit
    default_price: Decimal
    currency: str
    status: VariantStatus
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    category: str | None = Field(default=None, min_length=1, max_length=80)
    image_url: str | None = None
    has_profile_pin: bool | None = None
    status: ProductStatus | None = None


class ProductVariantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    duration_value: int | None = Field(default=None, gt=0)
    duration_unit: DurationUnit | None = None
    default_price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = None
    status: VariantStatus | None = None


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    category: str = Field(min_length=1, max_length=80)
    image_url: str | None = None
    has_profile_pin: bool = False
    status: ProductStatus = ProductStatus.ACTIVE


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    category: str
    image_url: str | None = None
    has_profile_pin: bool = False
    status: ProductStatus
    variants: list[ProductVariantRead] = []
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
