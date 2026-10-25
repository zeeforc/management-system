"""Database repository for renewal transactions and offers."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.renewals.models import RenewalOffer, RentalRenewal
from app.shared.pagination import PaginationParams


class RenewalRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_renewals(self, params: PaginationParams) -> tuple[list[RentalRenewal], int]:
        base_stmt = select(RentalRenewal)
        total = self.db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0
        items = list(
            self.db.scalars(
                base_stmt.order_by(RentalRenewal.created_at.desc())
                .offset(params.offset)
                .limit(params.page_size)
            ).all()
        )
        return items, int(total)

    def get_renewal(self, renewal_id: uuid.UUID, for_update: bool = False) -> RentalRenewal | None:
        stmt = select(RentalRenewal).where(RentalRenewal.id == renewal_id)
        if for_update:
            stmt = stmt.with_for_update()
        return self.db.scalar(stmt)

    def create_renewal(self, renewal: RentalRenewal) -> RentalRenewal:
        self.db.add(renewal)
        self.db.flush()
        return renewal

    def create_offer(self, offer: RenewalOffer) -> RenewalOffer:
        self.db.add(offer)
        self.db.flush()
        return offer
