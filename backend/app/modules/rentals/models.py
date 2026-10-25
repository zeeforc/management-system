"""SQLAlchemy model for rentals with transaction snapshots and indexes (Section 6.4 & 7)."""

from datetime import date
from decimal import Decimal
import uuid

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import ArchivableMixin, Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.shared.enums import DurationUnit, RenewalModel, RentalStatus
from app.shared.money import DEFAULT_CURRENCY


class Rental(Base, UUIDPrimaryKeyMixin, TimestampMixin, ArchivableMixin):
    __tablename__ = "rentals"
    __table_args__ = (
        CheckConstraint("expiration_date >= start_date", name="expiration_gte_start_date"),
        CheckConstraint("duration_value > 0", name="rental_duration_positive"),
        CheckConstraint("agreed_price >= 0", name="rental_agreed_price_non_negative"),
        Index("ix_rentals_expiration_date_status", "expiration_date", "status"),
        Index("ix_rentals_customer_id_expiration_date", "customer_id", "expiration_date"),
        Index("ix_rentals_product_id_status", "product_id", "status"),
        Index("ix_rentals_product_variant_id_status", "product_variant_id", "status"),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    product_variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_variants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiration_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiration_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    duration_value: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_unit: Mapped[DurationUnit] = mapped_column(String(32), nullable=False)
    agreed_price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default=DEFAULT_CURRENCY, nullable=False)
    status: Mapped[RentalStatus] = mapped_column(
        String(32),
        default=RentalStatus.ACTIVE,
        nullable=False,
    )
    renewal_model: Mapped[RenewalModel] = mapped_column(
        String(32),
        default=RenewalModel.CONTINUOUS,
        nullable=False,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
    )
