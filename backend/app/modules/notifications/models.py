"""SQLAlchemy models for notifications, attempts, responses, outbox_events, and idempotency_records (Section 6.8–6.12)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.shared.enums import (
    AttemptResultStatus,
    CustomerResponseType,
    NotificationStatus,
    OutboxStatus,
    ReminderStage,
)


class Notification(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint(
            "rental_id",
            "expiration_version",
            "reminder_stage",
            name="uq_notifications_rental_version_stage",
        ),
        Index("ix_notifications_status_scheduled_at", "status", "scheduled_at"),
    )

    rental_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rentals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reminder_stage: Mapped[ReminderStage] = mapped_column(String(16), nullable=False)
    expiration_version: Mapped[int] = mapped_column(Integer, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[NotificationStatus] = mapped_column(
        String(32),
        default=NotificationStatus.SCHEDULED,
        nullable=False,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    attempts: Mapped[list["NotificationAttempt"]] = relationship(
        "NotificationAttempt",
        back_populates="notification",
        lazy="selectin",
    )


class NotificationAttempt(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "notification_attempts"

    notification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notifications.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_status: Mapped[AttemptResultStatus] = mapped_column(String(32), nullable=False)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    notification: Mapped["Notification"] = relationship("Notification", back_populates="attempts")


class NotificationResponse(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "notification_responses"

    notification_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notifications.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
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
        index=True,
    )
    renewal_offer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("renewal_offers.id", ondelete="SET NULL"),
        nullable=True,
    )
    response_type: Mapped[CustomerResponseType] = mapped_column(String(32), nullable=False)
    responded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class OutboxEvent(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "outbox_events"
    __table_args__ = (Index("ix_outbox_events_status_available_at", "status", "available_at"),)

    event_type: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[OutboxStatus] = mapped_column(
        String(32),
        default=OutboxStatus.PENDING,
        nullable=False,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class IdempotencyRecord(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("scope", "idempotency_key", name="uq_idempotency_scope_key"),
    )

    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
