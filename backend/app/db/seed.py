"""Seed the initial owner administrator and OWNER role.

Usage:
    python -m app.db.seed
"""

import logging

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.modules.auth.models import AdminUser, Role, UserRole
from app.modules.auth.repository import AuthRepository
from app.shared.enums import RoleName

logger = logging.getLogger(__name__)


def seed_roles_and_owner() -> None:
    """Idempotently create the OWNER role and the initial administrator account."""
    db = SessionLocal()
    try:
        repo = AuthRepository(db)

        # ── Ensure OWNER role exists ──
        owner_role = repo.get_role_by_name(RoleName.OWNER)
        if owner_role is None:
            owner_role = Role(name=RoleName.OWNER, description="Full system owner with all permissions")
            db.add(owner_role)
            db.flush()
            print(f"✅ Created role: {RoleName.OWNER}")
        else:
            print(f"ℹ️  Role '{RoleName.OWNER}' already exists, skipping.")

        # ── Ensure STAFF role exists ──
        staff_role = repo.get_role_by_name(RoleName.STAFF)
        if staff_role is None:
            staff_role = Role(name=RoleName.STAFF, description="Staff with limited operational permissions")
            db.add(staff_role)
            db.flush()
            print(f"✅ Created role: {RoleName.STAFF}")
        else:
            print(f"ℹ️  Role '{RoleName.STAFF}' already exists, skipping.")

        # ── Ensure initial owner admin user exists ──
        email = settings.INITIAL_OWNER_EMAIL.lower().strip()
        existing_user = repo.get_by_email(email)
        if existing_user is None:
            password_hash = hash_password(settings.INITIAL_OWNER_PASSWORD)
            admin_user = AdminUser(
                email=email,
                password_hash=password_hash,
                is_active=True,
            )
            db.add(admin_user)
            db.flush()

            # Assign OWNER role
            user_role = UserRole(user_id=admin_user.id, role_id=owner_role.id)
            db.add(user_role)
            db.flush()

            print(f"✅ Created owner admin: {email}")
            print(f"   Password: (from INITIAL_OWNER_PASSWORD in .env)")
        else:
            print(f"ℹ️  Admin user '{email}' already exists, skipping.")

        db.commit()
        print("\n🎉 Seeding completed successfully!")
    except Exception as exc:
        db.rollback()
        print(f"❌ Seeding failed: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_roles_and_owner()
