"""Service for recording audit logs and managing non-secret system settings."""

from typing import Any
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging import request_id_ctx
from app.modules.audit.models import AuditLog, SystemSetting
from app.modules.audit.schemas import AuditLogRead, SystemSettingRead
from app.shared.enums import ActorType
from app.shared.pagination import PaginatedResponse, PaginationParams


class AuditService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record_event(
        self,
        *,
        actor_type: ActorType,
        actor_id: str | None,
        action: str,
        entity_type: str,
        entity_id: str,
        before_data: dict[str, Any] | None = None,
        after_data: dict[str, Any] | None = None,
    ) -> AuditLog:
        log = AuditLog(
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_data=before_data,
            after_data=after_data,
            request_id=request_id_ctx.get(),
        )
        self.db.add(log)
        self.db.flush()
        return log

    def list_logs(self, params: PaginationParams) -> PaginatedResponse[AuditLogRead]:
        base_stmt = select(AuditLog)
        total = self.db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0
        items = list(
            self.db.scalars(
                base_stmt.order_by(AuditLog.created_at.desc())
                .offset(params.offset)
                .limit(params.page_size)
            ).all()
        )
        return PaginatedResponse.create(
            items=[AuditLogRead.model_validate(item) for item in items],
            total=int(total),
            params=params,
        )

    def list_settings(self) -> list[SystemSettingRead]:
        items = list(self.db.scalars(select(SystemSetting).order_by(SystemSetting.key.asc())).all())
        return [SystemSettingRead.model_validate(item) for item in items]

    def upsert_setting(
        self,
        key: str,
        value: dict[str, Any],
        updated_by: uuid.UUID | None = None,
    ) -> SystemSettingRead:
        setting = self.db.scalar(select(SystemSetting).where(SystemSetting.key == key))
        if setting is None:
            setting = SystemSetting(key=key, value=value, updated_by=updated_by)
            self.db.add(setting)
        else:
            setting.value = value
            setting.updated_by = updated_by
        self.db.commit()
        self.db.refresh(setting)
        return SystemSettingRead.model_validate(setting)
