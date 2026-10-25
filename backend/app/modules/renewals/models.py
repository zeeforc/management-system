"""SQLAlchemy models for rental_renewals and renewal_offers (Section 6.5 & 6.6)."""

from datetime import date, datetime
from decimal import Decimal
import uuid

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.shared.enums import DurationUnit, RenewalModel, RenewalOfferStatus, RenewalStatus
from app.shared.money import DEFAULT_CURRENCY


class RentalRenewal(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "rental_renewals"
    __table_args__ = (
        CheckConstraint("new_expiration_date >= new_start_date", name="renewal_new_dates_valid"),
        CheckConstraint("duration_value > 0", name="renewal_duration_positive"),
        CheckConstraint("agreed_price >= 0", name="renewal_agreed_price_non_negative"),
    )

    rental_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rentals.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    previous_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    previous_expiration_date: Mapped[date] = mapped_column(Date, nullable=False)
    new_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    new_expiration_date: Mapped[date] = mapped_column(Date, nullable=False)
    duration_value: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_unit: Mapped[DurationUnit] = mapped_column(String(32), nullable=False)
    renewal_model: Mapped[RenewalModel] = mapped_column(String(32), nullable=False)
    agreed_price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default=DEFAULT_CURRENCY, nullable=False)
    status: Mapped[RenewalStatus] = mapped_column(
        String(32),
        default=RenewalStatus.PENDING,
        nullable=False,
        index=True,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class RenewalOffer(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "renewal_offers"
    __table_args__ = (
        CheckConstraint("offered_duration_value > 0", name="offer_duration_positive"),
        CheckConstraint("offered_price >= 0", name="offer_price_non_negative"),
        Index("ix_renewal_offers_customer_status_expires", "customer_id", "status", "expires_at"),
    )

    rental_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rentals.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    offered_duration_value: Mapped[int] = mapped_column(Integer, nullable=False)
    offered_duration_unit: Mapped[DurationUnit] = mapped_column(String(32), nullable=False)
    offered_price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default=DEFAULT_CURRENCY, nullable=False)
    renewal_model: Mapped[RenewalModel] = mapped_column(
        String(32),
        default=RenewalModel.CONTINUOUS,
        nullable=False,
    )
    status: Mapped[RenewalOfferStatus] = mapped_column(
        String(32),
        default=RenewalOfferStatus.ACTIVE,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
