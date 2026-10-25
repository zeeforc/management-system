"""FastAPI router for manual payments and verification."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.models import AdminUser
from app.modules.auth.service import get_current_admin
from app.modules.payments.schemas import PaymentCreate, PaymentRead
from app.modules.payments.service import PaymentService
from app.shared.pagination import PaginatedResponse, PaginationParams

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.get("", response_model=PaginatedResponse[PaymentRead])
def list_payments(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
) -> PaginatedResponse[PaymentRead]:
    service = PaymentService(db)
    return service.list_payments(PaginationParams(page=page, page_size=page_size))


@router.post("", response_model=PaymentRead, status_code=status.HTTP_201_CREATED)
def create_payment(
    payload: PaymentCreate,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
) -> PaymentRead:
    service = PaymentService(db)
    return service.create_payment(payload)


@router.post("/{payment_id}/verify", response_model=PaymentRead)
def verify_payment(
    payment_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> PaymentRead:
    service = PaymentService(db)
    return service.verify_payment(payment_id=payment_id, admin_id=admin.id)
