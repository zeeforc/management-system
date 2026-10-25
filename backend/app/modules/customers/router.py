"""FastAPI router for customers, Telegram linking tokens, and consent records."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.models import AdminUser
from app.modules.auth.service import get_current_admin
from app.modules.customers.schemas import (
    ConsentRead,
    ConsentRecordRequest,
    CustomerCreate,
    CustomerRead,
    CustomerUpdate,
    TelegramLinkTokenResponse,
)
from app.modules.customers.service import CustomerService
from app.shared.pagination import PaginatedResponse, PaginationParams

router = APIRouter(prefix="/customers", tags=["Customers"])


def _svc(db: Session, admin: AdminUser) -> CustomerService:
    return CustomerService(db, actor_id=str(admin.id))


@router.get("", response_model=PaginatedResponse[CustomerRead])
def list_customers(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> PaginatedResponse[CustomerRead]:
    return _svc(db, admin).list_customers(PaginationParams(page=page, page_size=page_size))


@router.post("", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
def create_customer(
    payload: CustomerCreate,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> CustomerRead:
    return _svc(db, admin).create_customer(payload)


@router.get("/{customer_id}", response_model=CustomerRead)
def get_customer(
    customer_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> CustomerRead:
    return _svc(db, admin).get_customer(customer_id)


@router.patch("/{customer_id}", response_model=CustomerRead)
def update_customer(
    customer_id: uuid.UUID,
    payload: CustomerUpdate,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> CustomerRead:
    return _svc(db, admin).update_customer(customer_id, payload)


@router.post("/{customer_id}/archive", response_model=CustomerRead)
def archive_customer(
    customer_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> CustomerRead:
    return _svc(db, admin).archive_customer(customer_id)


@router.post(
    "/{customer_id}/telegram-link-token",
    response_model=TelegramLinkTokenResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_telegram_link_token(
    customer_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> TelegramLinkTokenResponse:
    return _svc(db, admin).generate_telegram_link_token(customer_id)


@router.post(
    "/{customer_id}/consents",
    response_model=ConsentRead,
    status_code=status.HTTP_201_CREATED,
)
def record_consent(
    customer_id: uuid.UUID,
    payload: ConsentRecordRequest,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> ConsentRead:
    return _svc(db, admin).record_consent(customer_id, payload)
