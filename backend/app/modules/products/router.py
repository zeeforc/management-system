"""FastAPI router for products and product variants."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.models import AdminUser
from app.modules.auth.service import get_current_admin
from app.modules.products.schemas import (
    ProductCreate,
    ProductRead,
    ProductUpdate,
    ProductVariantCreate,
    ProductVariantRead,
    ProductVariantUpdate,
)
from app.modules.products.service import ProductService
from app.shared.pagination import PaginatedResponse, PaginationParams

router = APIRouter(prefix="/products", tags=["Products"])


def _svc(db: Session, admin: AdminUser) -> ProductService:
    return ProductService(db, actor_id=str(admin.id))


@router.get("", response_model=PaginatedResponse[ProductRead])
def list_products(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> PaginatedResponse[ProductRead]:
    return _svc(db, admin).list_products(PaginationParams(page=page, page_size=page_size))


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> ProductRead:
    return _svc(db, admin).create_product(payload)


@router.get("/{product_id}", response_model=ProductRead)
def get_product(
    product_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> ProductRead:
    return _svc(db, admin).get_product(product_id)


@router.patch("/{product_id}", response_model=ProductRead)
def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> ProductRead:
    return _svc(db, admin).update_product(product_id, payload)


@router.post("/{product_id}/archive", response_model=ProductRead)
def archive_product(
    product_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> ProductRead:
    return _svc(db, admin).archive_product(product_id)


@router.post("/variants", response_model=ProductVariantRead, status_code=status.HTTP_201_CREATED)
def create_variant(
    payload: ProductVariantCreate,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> ProductVariantRead:
    return _svc(db, admin).create_variant(payload)


@router.patch("/variants/{variant_id}", response_model=ProductVariantRead)
def update_variant(
    variant_id: uuid.UUID,
    payload: ProductVariantUpdate,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> ProductVariantRead:
    return _svc(db, admin).update_variant(variant_id, payload)


@router.post("/variants/{variant_id}/archive", response_model=ProductVariantRead)
def archive_variant(
    variant_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
) -> ProductVariantRead:
    return _svc(db, admin).archive_variant(variant_id)
