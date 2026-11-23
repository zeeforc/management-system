"""Temporary Telegram broadcast campaigns and per-recipient delivery state."""

import uuid
from datetime import datetime

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
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.shared.enums import TelegramBroadcastDeliveryStatus, TelegramBroadcastStatus


class TelegramBroadcast(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "telegram_broadcasts"
    __table_args__ = (
        Index("ix_telegram_broadcasts_status_created_at", "status", "created_at"),
    )

    created_by_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[TelegramBroadcastStatus] = mapped_column(
        String(32),
        default=TelegramBroadcastStatus.DRAFT,
        nullable=False,
    )
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    media_file_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    recipient_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sent_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ambiguous_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TelegramBroadcastRecipient(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "telegram_broadcast_recipients"
    __table_args__ = (
        UniqueConstraint("broadcast_id", "chat_id", name="uq_broadcast_recipient_chat"),
        Index("ix_broadcast_recipients_broadcast_status", "broadcast_id", "status"),
    )

    broadcast_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("telegram_broadcasts.id", ondelete="CASCADE"),
        nullable=False,
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
    )
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[TelegramBroadcastDeliveryStatus] = mapped_column(
        String(32),
        default=TelegramBroadcastDeliveryStatus.PENDING,
        nullable=False,
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
