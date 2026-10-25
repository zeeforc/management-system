"""FastAPI router for administrator authentication."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.models import AdminUser
from app.modules.auth.schemas import AdminUserRead, LoginRequest, TokenResponse
from app.modules.auth.service import AuthService, get_current_admin

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    service = AuthService(db)
    return service.authenticate_admin(payload)


@router.get("/me", response_model=AdminUserRead)
def get_me(current_admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
    return current_admin
