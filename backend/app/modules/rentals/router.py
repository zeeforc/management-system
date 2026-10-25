"""FastAPI router for rentals."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.models import AdminUser
from app.modules.auth.service import get_current_admin
from app.modules.rentals.schemas import RentalCreate, RentalRead, RentalUpdate
from app.modules.rentals.service import RentalService
from app.shared.pagination import PaginatedResponse, PaginationParams

router = APIRouter(prefix="/rentals", tags=["Rentals"])


def _svc(db: Session, admin: AdminUser) -> RentalService:
    return RentalService(db, actor_id=str(admin.id))


@router.get("", response_model=PaginatedResponse[RentalRead])
def list_rentals(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> PaginatedResponse[RentalRead]:
    return _svc(db, admin).list_rentals(PaginationParams(page=page, page_size=page_size))


@router.post("", response_model=RentalRead, status_code=status.HTTP_201_CREATED)
def create_rental(
    payload: RentalCreate,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> RentalRead:
    return _svc(db, admin).create_rental(payload, created_by=admin.id)


@router.get("/{rental_id}", response_model=RentalRead)
def get_rental(
    rental_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> RentalRead:
    return _svc(db, admin).get_rental(rental_id)


@router.patch("/{rental_id}", response_model=RentalRead)
def update_rental(
    rental_id: uuid.UUID,
    payload: RentalUpdate,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> RentalRead:
    return _svc(db, admin).update_rental(rental_id, payload)


@router.post("/{rental_id}/archive", response_model=RentalRead)
def archive_rental(
    rental_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> RentalRead:
    return _svc(db, admin).archive_rental(rental_id)
