"""FastAPI router for dashboard summary and analytics reports."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.models import AdminUser
from app.modules.auth.service import get_current_admin
from app.modules.reports.schemas import DashboardSummaryRead
from app.modules.reports.service import ReportService

router = APIRouter(prefix="/dashboard", tags=["Dashboard & Reports"])


@router.get("/summary", response_model=DashboardSummaryRead)
def get_dashboard_summary(
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
) -> DashboardSummaryRead:
    service = ReportService(db)
    return service.get_dashboard_summary()
