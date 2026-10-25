"""FastAPI router for notification logs and reminder scheduling."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.models import AdminUser
from app.modules.auth.service import get_current_admin
from app.modules.notifications.schemas import NotificationRead
from app.modules.notifications.service import NotificationService
from app.shared.pagination import PaginatedResponse, PaginationParams

router = APIRouter(tags=["Notifications"])


@router.get("/notifications", response_model=PaginatedResponse[NotificationRead])
def list_notifications(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
) -> PaginatedResponse[NotificationRead]:
    service = NotificationService(db)
    return service.list_notifications(PaginationParams(page=page, page_size=page_size))


@router.post(
    "/rentals/{rental_id}/notifications",
    response_model=list[NotificationRead],
    status_code=status.HTTP_201_CREATED,
)
def schedule_rental_notifications(
    rental_id: uuid.UUID,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
) -> list[NotificationRead]:
    service = NotificationService(db)
    return service.schedule_rental_reminders(rental_id)
