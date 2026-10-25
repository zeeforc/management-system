"""SQLAlchemy models for customers, notification consents, and Telegram link tokens (Section 6.3)."""

from datetime import datetime
import uuid

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import ArchivableMixin, Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.shared.enums import ConsentStatus, ConsentType, CustomerStatus


class Customer(Base, UUIDPrimaryKeyMixin, TimestampMixin, ArchivableMixin):
    __tablename__ = "customers"

    display_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    telegram_username: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    status: Mapped[CustomerStatus] = mapped_column(
        String(32),
        default=CustomerStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    consents: Mapped[list["NotificationConsent"]] = relationship(
        "NotificationConsent",
        back_populates="customer",
        lazy="selectin",
    )


class NotificationConsent(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "notification_consents"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    consent_type: Mapped[ConsentType] = mapped_column(String(64), nullable=False)
    consent_status: Mapped[ConsentStatus] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    customer: Mapped["Customer"] = relationship("Customer", back_populates="consents")


class TelegramLinkToken(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "telegram_link_tokens"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
