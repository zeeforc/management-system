from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

from app.core.encryption import encrypt_credential
from app.modules.notifications.delivery import (
    build_admin_reminder_message,
    build_reminder_message,
)
from app.shared.datetime_utils import current_wib_date
from app.shared.enums import ConsentStatus, ReminderStage, RentalStatus


def _reminder_records():
    today = current_wib_date()
    notification = SimpleNamespace(
        id="notification-id",
        rental_id="rental-id",
        customer_id="customer-id",
        reminder_stage=ReminderStage.H5,
        expiration_version=1,
    )
    rental = SimpleNamespace(
        id="rental-id",
        customer_id="customer-id",
        product_id="product-id",
        product_variant_id="variant-id",
        start_date=today,
        expiration_date=today + timedelta(days=5),
        expiration_version=1,
        duration_value=1,
        duration_unit="MONTHS",
        agreed_price=Decimal("30000"),
        account_email_encrypted=encrypt_credential("account@example.com"),
        profile_encrypted=encrypt_credential("Profile A"),
        pin_encrypted=encrypt_credential("1234"),
        status=RentalStatus.ACTIVE,
        archived_at=None,
    )
    customer = SimpleNamespace(
        id="customer-id",
        display_name="Test Customer",
        telegram_username="test_customer",
        telegram_chat_id=1234,
        status="ACTIVE",
        archived_at=None,
    )
    product = SimpleNamespace(id="product-id", name="Streaming")
    variant = SimpleNamespace(id="variant-id", name="Premium")
    return notification, rental, customer, product, variant


def test_admin_reminder_contains_private_account_details() -> None:
    records = _reminder_records()
    db = Mock()
    db.get.side_effect = records

    text = build_admin_reminder_message(db, records[0].id)

    assert "account@example.com" in text
    assert "Profile A" in text
    assert "1234" in text
    assert "@test_customer" in text
    assert "1 bulan" in text


def test_customer_reminder_never_includes_account_credentials() -> None:
    records = _reminder_records()
    db = Mock()
    db.get.side_effect = records
    db.scalar.side_effect = [
        SimpleNamespace(consent_status=ConsentStatus.GRANTED),
        SimpleNamespace(consent_status=ConsentStatus.REVOKED),
    ]

    _, text, _ = build_reminder_message(db, records[0].id)

    assert "Test Customer" in text
    assert "Streaming" in text
    assert "account@example.com" not in text
    assert "Profile A" not in text
    assert "1234" not in text
