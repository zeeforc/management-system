"""Repository for administrator users and roles."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models import AdminUser, Role


class AuthRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_email(self, email: str) -> AdminUser | None:
        stmt = select(AdminUser).where(AdminUser.email == email.lower().strip())
        return self.db.scalar(stmt)

    def get_by_id(self, user_id: uuid.UUID) -> AdminUser | None:
        stmt = select(AdminUser).where(AdminUser.id == user_id)
        return self.db.scalar(stmt)

    def get_role_by_name(self, name: str) -> Role | None:
        stmt = select(Role).where(Role.name == name)
        return self.db.scalar(stmt)
