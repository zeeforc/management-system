"""Central model registry importing all SQLAlchemy models for Alembic autogenerate."""

from app.modules.audit.models import AuditLog, SystemSetting
from app.modules.auth.models import AdminUser, Role, UserRole
from app.modules.customers.models import (
    Customer,
    NotificationConsent,
    StoreFeedback,
    TelegramLinkToken,
)
from app.modules.notifications.models import (
    IdempotencyRecord,
    Notification,
    NotificationAttempt,
    NotificationResponse,
    OutboxEvent,
)
from app.modules.payments.models import Payment
from app.modules.products.models import Product, ProductVariant
from app.modules.renewals.models import RenewalOffer, RentalRenewal
from app.modules.rentals.models import Rental

__all__ = [
    "AdminUser",
    "Role",
    "UserRole",
    "Product",
    "ProductVariant",
    "Customer",
    "NotificationConsent",
    "TelegramLinkToken",
    "StoreFeedback",
    "Rental",
    "RentalRenewal",
    "RenewalOffer",
    "Payment",
    "Notification",
    "NotificationAttempt",
    "NotificationResponse",
    "OutboxEvent",
    "IdempotencyRecord",
    "AuditLog",
    "SystemSetting",
]
