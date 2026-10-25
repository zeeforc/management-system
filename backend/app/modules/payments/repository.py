"""Database repository for payments."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.payments.models import Payment
from app.shared.pagination import PaginationParams


class PaymentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_payments(self, params: PaginationParams) -> tuple[list[Payment], int]:
        base_stmt = select(Payment)
        total = self.db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0
        items = list(
            self.db.scalars(
                base_stmt.order_by(Payment.created_at.desc())
                .offset(params.offset)
                .limit(params.page_size)
            ).all()
        )
        return items, int(total)

    def get_payment(self, payment_id: uuid.UUID, for_update: bool = False) -> Payment | None:
        stmt = select(Payment).where(Payment.id == payment_id)
        if for_update:
            stmt = stmt.with_for_update()
        return self.db.scalar(stmt)

    def create_payment(self, payment: Payment) -> Payment:
        self.db.add(payment)
        self.db.flush()
        return payment
