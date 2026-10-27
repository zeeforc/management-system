"""Business service for managing products and product variants."""

import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError, NotFoundError
from app.modules.audit.models import AuditLog
from app.modules.products.models import Product, ProductVariant
from app.modules.products.repository import ProductRepository
from app.modules.products.schemas import (
    ProductCreate,
    ProductRead,
    ProductUpdate,
    ProductVariantCreate,
    ProductVariantRead,
    ProductVariantUpdate,
)
from app.shared.datetime_utils import utc_now
from app.shared.enums import ActorType
from app.shared.money import normalize_money, validate_currency
from app.shared.pagination import PaginatedResponse, PaginationParams


class ProductService:
    def __init__(self, db: Session, actor_id: str | None = None) -> None:
        self.db = db
        self.repo = ProductRepository(db)
        self.actor_id = actor_id

    def _audit(self, action: str, entity_id: str, before: dict | None, after: dict | None) -> None:
        log = AuditLog(
            actor_type=ActorType.ADMIN,
            actor_id=self.actor_id,
            action=action,
            entity_type="Product",
            entity_id=entity_id,
            before_data=before,
            after_data=after,
        )
        self.db.add(log)

    def list_products(self, params: PaginationParams) -> PaginatedResponse[ProductRead]:
        items, total = self.repo.list_products(params)
        return PaginatedResponse.create(
            items=[ProductRead.model_validate(item) for item in items],
            total=total,
            params=params,
        )

    def get_product(self, product_id: uuid.UUID) -> ProductRead:
        product = self.repo.get_product(product_id)
        if product is None:
            raise NotFoundError("Product", product_id)
        return ProductRead.model_validate(product)

    def create_product(self, payload: ProductCreate) -> ProductRead:
        product = Product(
            name=payload.name.strip(),
            description=payload.description,
            category=payload.category.strip(),
            image_url=payload.image_url,
            has_profile_pin=payload.has_profile_pin,
            status=payload.status,
        )
        self.repo.create_product(product)
        self._audit(
            "product.created",
            str(product.id),
            None,
            {"name": product.name, "status": product.status},
        )
        self.db.commit()
        self.db.refresh(product)
        return ProductRead.model_validate(product)

    def update_product(self, product_id: uuid.UUID, payload: ProductUpdate) -> ProductRead:
        product = self.repo.get_product(product_id)
        if product is None:
            raise NotFoundError("Product", product_id)
        before = {
            "name": product.name,
            "status": product.status,
            "category": product.category,
        }
        if payload.name is not None:
            product.name = payload.name.strip()
        if "description" in payload.model_fields_set:
            product.description = payload.description
        if payload.category is not None:
            product.category = payload.category.strip()
        if "image_url" in payload.model_fields_set:
            product.image_url = payload.image_url
        if payload.has_profile_pin is not None:
            product.has_profile_pin = payload.has_profile_pin
        if payload.status is not None:
            product.status = payload.status
        self._audit(
            "product.updated",
            str(product.id),
            before,
            {"name": product.name, "status": product.status},
        )
        self.db.commit()
        self.db.refresh(product)
        return ProductRead.model_validate(product)

    def archive_product(self, product_id: uuid.UUID) -> ProductRead:
        product = self.repo.get_product(product_id)
        if product is None:
            raise NotFoundError("Product", product_id)
        if product.archived_at is not None:
            raise BusinessRuleError("Product is already archived.")
        before = {"status": product.status, "archived_at": None}
        product.archived_at = utc_now()
        self._audit(
            "product.archived",
            str(product.id),
            before,
            {"archived_at": str(product.archived_at)},
        )
        self.db.commit()
        self.db.refresh(product)
        return ProductRead.model_validate(product)

    def create_variant(self, payload: ProductVariantCreate) -> ProductVariantRead:
        product = self.repo.get_product(payload.product_id)
        if product is None:
            raise NotFoundError("Product", payload.product_id)
        currency = validate_currency(payload.currency)
        price = normalize_money(payload.default_price, currency)
        variant = ProductVariant(
            product_id=payload.product_id,
            name=payload.name.strip(),
            duration_value=payload.duration_value,
            duration_unit=payload.duration_unit,
            default_price=price,
            currency=currency,
            status=payload.status,
        )
        self.repo.create_variant(variant)
        self._audit(
            "variant.created",
            str(variant.id),
            None,
            {"name": variant.name, "product_id": str(variant.product_id)},
        )
        self.db.commit()
        self.db.refresh(variant)
        return ProductVariantRead.model_validate(variant)

    def update_variant(
        self,
        variant_id: uuid.UUID,
        payload: ProductVariantUpdate,
    ) -> ProductVariantRead:
        variant = self.repo.get_variant(variant_id)
        if variant is None:
            raise NotFoundError("ProductVariant", variant_id)
        before = {
            "name": variant.name,
            "default_price": str(variant.default_price),
            "status": variant.status,
        }
        if payload.name is not None:
            variant.name = payload.name.strip()
        if payload.duration_value is not None:
            variant.duration_value = payload.duration_value
        if payload.duration_unit is not None:
            variant.duration_unit = payload.duration_unit
        if payload.default_price is not None:
            currency = validate_currency(payload.currency or variant.currency)
            variant.default_price = normalize_money(payload.default_price, currency)
            variant.currency = currency
        if payload.status is not None:
            variant.status = payload.status
        self._audit(
            "variant.updated",
            str(variant.id),
            before,
            {"name": variant.name, "status": variant.status},
        )
        self.db.commit()
        self.db.refresh(variant)
        return ProductVariantRead.model_validate(variant)

    def archive_variant(self, variant_id: uuid.UUID) -> ProductVariantRead:
        variant = self.repo.get_variant(variant_id)
        if variant is None:
            raise NotFoundError("ProductVariant", variant_id)
        if variant.archived_at is not None:
            raise BusinessRuleError("Variant is already archived.")
        variant.archived_at = utc_now()
        self._audit(
            "variant.archived",
            str(variant.id),
            None,
            {"archived_at": str(variant.archived_at)},
        )
        self.db.commit()
        self.db.refresh(variant)
        return ProductVariantRead.model_validate(variant)
