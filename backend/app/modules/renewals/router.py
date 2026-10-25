"""FastAPI router for renewal requests and renewal offers."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.models import AdminUser
from app.modules.auth.service import get_current_admin
from app.modules.renewals.schemas import (
    RenewalApprovalRequest,
    RenewalOfferCreate,
    RenewalOfferRead,
    RenewalRead,
    RenewalRequestCreate,
)
from app.modules.renewals.service import RenewalService
from app.shared.pagination import PaginatedResponse, PaginationParams

router = APIRouter(tags=["Renewals"])


@router.get("/renewals", response_model=PaginatedResponse[RenewalRead])
def list_renewals(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
) -> PaginatedResponse[RenewalRead]:
    service = RenewalService(db)
    return service.list_renewals(PaginationParams(page=page, page_size=page_size))


@router.post(
    "/rentals/{rental_id}/renewals",
    response_model=RenewalRead,
    status_code=status.HTTP_201_CREATED,
)
def create_renewal_request(
    rental_id: uuid.UUID,
    payload: RenewalRequestCreate,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> RenewalRead:
    service = RenewalService(db)
    return service.create_renewal_request(rental_id, payload, created_by=admin.id)


@router.post(
    "/renewal-offers",
    response_model=RenewalOfferRead,
    status_code=status.HTTP_201_CREATED,
)
def create_renewal_offer(
    payload: RenewalOfferCreate,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
) -> RenewalOfferRead:
    service = RenewalService(db)
    return service.create_offer(payload)


@router.post("/renewals/{renewal_id}/approve", response_model=RenewalRead)
def approve_renewal(
    renewal_id: uuid.UUID,
    payload: RenewalApprovalRequest,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> RenewalRead:
    return RenewalService(db).approve_renewal(renewal_id, payload, admin.id)


@router.post("/renewals/{renewal_id}/reject", response_model=RenewalRead)
def reject_renewal(
    renewal_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> RenewalRead:
    return RenewalService(db).reject_renewal(renewal_id, admin.id)


@router.post("/renewals/{renewal_id}/complete", response_model=RenewalRead)
def complete_renewal(
    renewal_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> RenewalRead:
    return RenewalService(db).complete_renewal(renewal_id, admin.id)
