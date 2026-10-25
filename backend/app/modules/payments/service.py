"""Business service for recording and verifying payments transactionally (Section 8.2)."""

import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.modules.payments.models import Payment
from app.modules.payments.repository import PaymentRepository
from app.modules.payments.schemas import PaymentCreate, PaymentRead
from app.shared.datetime_utils import utc_now
from app.shared.enums import PaymentStatus
from app.shared.money import normalize_money, validate_currency
from app.shared.pagination import PaginatedResponse, PaginationParams


class PaymentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = PaymentRepository(db)

    def list_payments(self, params: PaginationParams) -> PaginatedResponse[PaymentRead]:
        items, total = self.repo.list_payments(params)
        return PaginatedResponse.create(
            items=[PaymentRead.model_validate(item) for item in items],
            total=total,
            params=params,
        )

    def create_payment(self, payload: PaymentCreate) -> PaymentRead:
        currency = validate_currency(payload.currency)
        amount = normalize_money(payload.amount, currency)
        payment = Payment(
            customer_id=payload.customer_id,
            rental_id=payload.rental_id,
            renewal_id=payload.renewal_id,
            amount=amount,
            currency=currency,
            payment_method=payload.payment_method,
            status=PaymentStatus.PENDING,
            payment_reference=payload.payment_reference,
            paid_at=payload.paid_at,
        )
        self.repo.create_payment(payment)
        self.db.commit()
        self.db.refresh(payment)
        return PaymentRead.model_validate(payment)

    def verify_payment(self, payment_id: uuid.UUID, admin_id: uuid.UUID) -> PaymentRead:
        payment = self.repo.get_payment(payment_id, for_update=True)
        if payment is None:
            raise NotFoundError("Payment", payment_id)

        if payment.status == PaymentStatus.PAID and payment.verified_at is not None:
            raise ConflictError("Payment has already been verified.")

        now = utc_now()
        payment.status = PaymentStatus.PAID
        payment.verified_at = now
        payment.verified_by = admin_id
        if payment.paid_at is None:
            payment.paid_at = now

        self.db.commit()
        self.db.refresh(payment)
        return PaymentRead.model_validate(payment)
