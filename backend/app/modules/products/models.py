"""SQLAlchemy models for products and product variants (Section 6.2)."""

from decimal import Decimal
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import ArchivableMixin, Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.shared.enums import DurationUnit, ProductStatus, VariantStatus
from app.shared.money import DEFAULT_CURRENCY


class Product(Base, UUIDPrimaryKeyMixin, TimestampMixin, ArchivableMixin):
    __tablename__ = "products"

    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[ProductStatus] = mapped_column(
        String(32),
        default=ProductStatus.ACTIVE,
        nullable=False,
        index=True,
    )

    variants: Mapped[list["ProductVariant"]] = relationship(
        "ProductVariant",
        back_populates="product",
        lazy="selectin",
    )


class ProductVariant(Base, UUIDPrimaryKeyMixin, TimestampMixin, ArchivableMixin):
    __tablename__ = "product_variants"
    __table_args__ = (
        CheckConstraint("duration_value > 0", name="duration_value_positive"),
        CheckConstraint("default_price >= 0", name="default_price_non_negative"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    duration_value: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_unit: Mapped[DurationUnit] = mapped_column(String(32), nullable=False)
    default_price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default=DEFAULT_CURRENCY, nullable=False)
    status: Mapped[VariantStatus] = mapped_column(
        String(32),
        default=VariantStatus.ACTIVE,
        nullable=False,
        index=True,
    )

    product: Mapped["Product"] = relationship("Product", back_populates="variants")
