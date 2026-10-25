"""Role-based access control and Telegram administrator authorization helpers."""

from app.core.config import settings
from app.core.exceptions import PermissionDeniedError
from app.shared.enums import RoleName


def is_telegram_admin(telegram_user_id: int | None) -> bool:
    """Check whether a Telegram numeric user ID is in the configured admin allowlist."""
    if telegram_user_id is None:
        return False
    return telegram_user_id in settings.TELEGRAM_ADMIN_USER_IDS


def ensure_has_role(user_roles: list[str], allowed_roles: tuple[RoleName, ...]) -> None:
    """Verify that the user holds at least one of the allowed roles."""
    allowed_set = {role.value for role in allowed_roles}
    if not any(r in allowed_set for r in user_roles):
        raise PermissionDeniedError()
