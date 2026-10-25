"""SQLAlchemy models for audit_logs and system_settings (Section 6.13 & 6.14)."""

from datetime import datetime
from typing import Any
import uuid

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.shared.enums import ActorType


class AuditLog(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_entity_type_id_created", "entity_type", "entity_id", "created_at"),
    )

    actor_type: Mapped[ActorType] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    before_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(96), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
