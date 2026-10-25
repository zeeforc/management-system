"""FastAPI router for audit logs and system settings."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.audit.schemas import AuditLogRead, SystemSettingRead, SystemSettingUpsert
from app.modules.audit.service import AuditService
from app.modules.auth.models import AdminUser
from app.modules.auth.service import get_current_admin
from app.shared.pagination import PaginatedResponse, PaginationParams

router = APIRouter(tags=["Audit & Settings"])


@router.get("/audit-logs", response_model=PaginatedResponse[AuditLogRead])
def list_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
) -> PaginatedResponse[AuditLogRead]:
    service = AuditService(db)
    return service.list_logs(PaginationParams(page=page, page_size=page_size))


@router.get("/settings", response_model=list[SystemSettingRead])
def list_settings(
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
) -> list[SystemSettingRead]:
    service = AuditService(db)
    return service.list_settings()


@router.put("/settings/{key}", response_model=SystemSettingRead)
def upsert_setting(
    key: str,
    payload: SystemSettingUpsert,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> SystemSettingRead:
    service = AuditService(db)
    return service.upsert_setting(key=key, value=payload.value, updated_by=admin.id)
