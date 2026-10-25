"""Database repository for products and product variants."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.products.models import Product, ProductVariant
from app.shared.pagination import PaginationParams


class ProductRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_products(self, params: PaginationParams) -> tuple[list[Product], int]:
        base_stmt = select(Product).where(Product.archived_at.is_(None))
        total = self.db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0
        items = list(
            self.db.scalars(
                base_stmt.order_by(Product.created_at.desc())
                .offset(params.offset)
                .limit(params.page_size)
            ).all()
        )
        return items, int(total)

    def get_product(self, product_id: uuid.UUID) -> Product | None:
        return self.db.scalar(select(Product).where(Product.id == product_id))

    def create_product(self, product: Product) -> Product:
        self.db.add(product)
        self.db.flush()
        return product

    def get_variant(self, variant_id: uuid.UUID) -> ProductVariant | None:
        return self.db.scalar(select(ProductVariant).where(ProductVariant.id == variant_id))

    def create_variant(self, variant: ProductVariant) -> ProductVariant:
        self.db.add(variant)
        self.db.flush()
        return variant
