"""Database repository for rentals."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.rentals.models import Rental
from app.shared.pagination import PaginationParams


class RentalRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_rentals(self, params: PaginationParams) -> tuple[list[Rental], int]:
        base_stmt = select(Rental).where(Rental.archived_at.is_(None))
        total = self.db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0
        items = list(
            self.db.scalars(
                base_stmt.order_by(Rental.expiration_date.asc(), Rental.created_at.desc())
                .offset(params.offset)
                .limit(params.page_size)
            ).all()
        )
        return items, int(total)

    def get_rental(self, rental_id: uuid.UUID, for_update: bool = False) -> Rental | None:
        stmt = select(Rental).where(Rental.id == rental_id)
        if for_update:
            stmt = stmt.with_for_update()
        return self.db.scalar(stmt)

    def create_rental(self, rental: Rental) -> Rental:
        self.db.add(rental)
        self.db.flush()
        return rental
