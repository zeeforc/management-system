"""SQLAlchemy model for payments (Section 6.7 & 7)."""

from datetime import datetime
from decimal import Decimal
import uuid

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.shared.enums import PaymentMethod, PaymentStatus
from app.shared.money import DEFAULT_CURRENCY


class Payment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="payment_amount_non_negative"),
        Index("ix_payments_status_created_at", "status", "created_at"),
        Index("ix_payments_rental_id", "rental_id"),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    rental_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rentals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    renewal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rental_renewals.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default=DEFAULT_CURRENCY, nullable=False)
    payment_method: Mapped[PaymentMethod] = mapped_column(String(32), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        String(32),
        default=PaymentStatus.PENDING,
        nullable=False,
    )
    payment_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
    )
