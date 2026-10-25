"""Authentication service and FastAPI current-admin dependencies."""

import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import create_access_token, decode_access_token, verify_password
from app.db.session import get_db
from app.modules.auth.models import AdminUser
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import LoginRequest, TokenResponse
from app.shared.datetime_utils import utc_now

bearer_scheme = HTTPBearer(auto_error=False)


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AuthRepository(db)

    def authenticate_admin(self, payload: LoginRequest) -> TokenResponse:
        user = self.repo.get_by_email(payload.email)
        if user is None or not verify_password(payload.password, user.password_hash):
            raise AuthenticationError("Invalid email or password.")
        if not user.is_active:
            raise PermissionDeniedError("Administrator account is inactive.")

        user.last_login_at = utc_now()
        self.db.commit()

        role_names = [role.name for role in user.roles]
        token = create_access_token(subject=str(user.id), roles=role_names)
        return TokenResponse(
            access_token=token,
            expires_in_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        )


def get_current_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> AdminUser:
    """Resolve and validate the currently authenticated administrator."""
    if credentials is None:
        raise AuthenticationError("Missing bearer token.")
    try:
        payload = decode_access_token(credentials.credentials)
        sub = payload.get("sub")
        if not sub:
            raise AuthenticationError("Invalid token subject.")
        user_id = uuid.UUID(str(sub))
    except (jwt.PyJWTError, ValueError) as exc:
        raise AuthenticationError("Invalid or expired access token.") from exc

    repo = AuthRepository(db)
    user = repo.get_by_id(user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Administrator account not found or inactive.")
    return user
