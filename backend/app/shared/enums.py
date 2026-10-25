"""Centralized domain enumerations matching the architectural specification."""

from enum import StrEnum


class RoleName(StrEnum):
    OWNER = "OWNER"
    STAFF = "STAFF"


class ProductStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"


class VariantStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"


class DurationUnit(StrEnum):
    DAYS = "DAYS"
    WEEKS = "WEEKS"
    MONTHS = "MONTHS"
    YEARS = "YEARS"


class CustomerStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"
    ARCHIVED = "ARCHIVED"


class ConsentType(StrEnum):
    TELEGRAM_REMINDERS = "TELEGRAM_REMINDERS"
    TELEGRAM_RENEWAL_OFFERS = "TELEGRAM_RENEWAL_OFFERS"


class ConsentStatus(StrEnum):
    GRANTED = "GRANTED"
    REVOKED = "REVOKED"


class RentalStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    ACTIVE = "ACTIVE"
    EXPIRING_SOON = "EXPIRING_SOON"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class ExpirationWarningState(StrEnum):
    NONE = "NONE"
    EXPIRING_H5 = "EXPIRING_H5"
    EXPIRING_H3 = "EXPIRING_H3"
    EXPIRING_H1 = "EXPIRING_H1"
    EXPIRED = "EXPIRED"


class RenewalModel(StrEnum):
    CONTINUOUS = "CONTINUOUS"
    IMMEDIATE = "IMMEDIATE"


class RenewalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class RenewalOfferStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SELECTED = "SELECTED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"
    CANCELLED = "CANCELLED"


class PaymentStatus(StrEnum):
    PENDING = "PENDING"
    PAID = "PAID"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"


class PaymentMethod(StrEnum):
    BANK_TRANSFER = "BANK_TRANSFER"
    QRIS = "QRIS"
    EWALLET = "EWALLET"
    CASH = "CASH"
    MANUAL_OTHER = "MANUAL_OTHER"


class ReminderStage(StrEnum):
    H5 = "H5"
    H3 = "H3"
    H1 = "H1"


class NotificationStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    QUEUED = "QUEUED"
    SENT = "SENT"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_PERMANENT = "FAILED_PERMANENT"
    AMBIGUOUS = "AMBIGUOUS"
    CANCELLED = "CANCELLED"


class AttemptResultStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_PERMANENT = "FAILED_PERMANENT"
    AMBIGUOUS = "AMBIGUOUS"


class CustomerResponseType(StrEnum):
    SELECT_OFFER = "SELECT_OFFER"
    DECLINE_OFFER = "DECLINE_OFFER"


class OutboxStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class ActorType(StrEnum):
    ADMIN = "ADMIN"
    CUSTOMER = "CUSTOMER"
    SYSTEM = "SYSTEM"
    TELEGRAM_BOT = "TELEGRAM_BOT"
