"""Database repository for rentals."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.customers.models import Customer
from app.modules.products.models import Product, ProductVariant
from app.modules.rentals.models import Rental
from app.shared.pagination import PaginationParams


class RentalRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_rentals(self, params: PaginationParams) -> tuple[list[tuple], int]:
        base_stmt = select(Rental).where(Rental.archived_at.is_(None))
        total = self.db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0
        stmt = (
            select(
                Rental,
                Customer.display_name,
                Product.name,
                ProductVariant.name,
            )
            .join(Customer, Customer.id == Rental.customer_id)
            .join(Product, Product.id == Rental.product_id)
            .join(ProductVariant, ProductVariant.id == Rental.product_variant_id)
            .where(Rental.archived_at.is_(None))
            .order_by(Rental.expiration_date.asc(), Rental.created_at.desc())
            .offset(params.offset)
            .limit(params.page_size)
        )
        items = list(self.db.execute(stmt).all())
        return items, int(total)

    def get_rental(self, rental_id: uuid.UUID, for_update: bool = False) -> Rental | None:
        stmt = select(Rental).where(Rental.id == rental_id)
        if for_update:
            stmt = stmt.with_for_update()
        return self.db.scalar(stmt)

    def get_rentals_for_update(self, rental_ids: set[uuid.UUID]) -> dict[uuid.UUID, Rental]:
        if not rental_ids:
            return {}
        stmt = select(Rental).where(Rental.id.in_(rental_ids)).with_for_update()
        return {rental.id: rental for rental in self.db.scalars(stmt).all()}

    def create_rental(self, rental: Rental) -> Rental:
        self.db.add(rental)
        self.db.flush()
        return rental
