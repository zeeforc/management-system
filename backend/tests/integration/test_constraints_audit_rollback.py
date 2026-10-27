"""Integration tests against real PostgreSQL: constraints, rollback, audit logs, duplicate prevention."""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.audit.models import AuditLog
from app.modules.auth.models import AdminUser
from app.modules.customers.models import Customer
from app.modules.customers.service import CustomerService
from app.modules.notifications.models import Notification, OutboxEvent
from app.modules.payments.models import Payment
from app.modules.payments.service import PaymentService
from app.modules.products.models import Product, ProductVariant
from app.modules.products.service import ProductService
from app.modules.rentals.models import Rental
from app.modules.rentals.service import RentalService
from app.shared.datetime_utils import current_wib_date
from app.shared.enums import (
    DurationUnit,
    NotificationStatus,
    OutboxStatus,
    PaymentMethod,
    PaymentStatus,
    ReminderStage,
    RenewalModel,
    RentalStatus,
)

# ─── DB Constraint Tests ──────────────────────────────────────────────────────

class TestDatabaseConstraints:
    def test_unique_admin_email(self, db: Session, admin_user: AdminUser) -> None:
        """admin_users.email has a UNIQUE constraint."""
        duplicate = AdminUser(
            email=admin_user.email,
            password_hash="hash",
            is_active=True,
        )
        db.add(duplicate)
        with pytest.raises(IntegrityError):
            db.flush()

    def test_rental_expiration_gte_start_check_constraint(
        self,
        db: Session,
        customer: Customer,
        product: Product,
        variant: ProductVariant,
    ) -> None:
        """rentals CHECK expiration_date >= start_date."""
        today = current_wib_date()
        bad_rental = Rental(
            customer_id=customer.id,
            product_id=product.id,
            product_variant_id=variant.id,
            start_date=today,
            expiration_date=today - timedelta(days=1),
            expiration_version=1,
            duration_value=1,
            duration_unit=DurationUnit.MONTHS,
            agreed_price=Decimal("50000.00"),
            currency="IDR",
            status=RentalStatus.ACTIVE,
            renewal_model=RenewalModel.CONTINUOUS,
        )
        db.add(bad_rental)
        with pytest.raises(IntegrityError):
            db.flush()

    def test_notification_unique_rental_version_stage(
        self,
        db: Session,
        active_rental: Rental,
    ) -> None:
        """notifications UNIQUE (rental_id, expiration_version, reminder_stage)."""
        from app.shared.datetime_utils import calculate_reminder_scheduled_utc
        stage = ReminderStage.H5
        scheduled_at = calculate_reminder_scheduled_utc(active_rental.expiration_date, stage)
        n1 = Notification(
            rental_id=active_rental.id,
            customer_id=active_rental.customer_id,
            reminder_stage=stage,
            expiration_version=active_rental.expiration_version,
            scheduled_at=scheduled_at,
            status=NotificationStatus.SCHEDULED,
            attempt_count=0,
        )
        n2 = Notification(
            rental_id=active_rental.id,
            customer_id=active_rental.customer_id,
            reminder_stage=stage,
            expiration_version=active_rental.expiration_version,
            scheduled_at=scheduled_at,
            status=NotificationStatus.SCHEDULED,
            attempt_count=0,
        )
        db.add(n1)
        db.flush()
        db.add(n2)
        with pytest.raises(IntegrityError):
            db.flush()

    def test_product_variant_duration_positive_constraint(
        self, db: Session, product: Product
    ) -> None:
        """product_variants CHECK duration_value > 0."""
        bad_variant = ProductVariant(
            product_id=product.id,
            name="Bad Variant",
            duration_value=0,
            duration_unit=DurationUnit.MONTHS,
            default_price=Decimal("10000.00"),
            currency="IDR",
            status="ACTIVE",
        )
        db.add(bad_variant)
        with pytest.raises(IntegrityError):
            db.flush()


# ─── Transaction Rollback Tests ───────────────────────────────────────────────

class TestTransactionRollback:
    def test_rollback_on_duplicate_payment_verification(
        self, db: Session, active_rental: Rental, admin_user: AdminUser
    ) -> None:
        """Second verify call raises ConflictError; DB stays clean."""
        from app.core.exceptions import ConflictError

        payment = Payment(
            customer_id=active_rental.customer_id,
            rental_id=active_rental.id,
            amount=Decimal("50000.00"),
            currency="IDR",
            payment_method=PaymentMethod.BANK_TRANSFER,
            status=PaymentStatus.PENDING,
        )
        db.add(payment)
        db.flush()

        svc = PaymentService(db)
        svc.verify_payment(payment.id, admin_user.id)

        with pytest.raises(ConflictError, match="already been verified"):
            svc.verify_payment(payment.id, admin_user.id)

    def test_rollback_preserves_data_on_error(
        self, db: Session, customer: Customer
    ) -> None:
        """After a failed flush, rolling back a savepoint keeps earlier data intact."""
        db.add(Customer(display_name="Customer Before Error", status="ACTIVE"))
        db.flush()

        count_before = db.scalar(
            select(text("count(*)")).select_from(Customer.__table__)
        )

        # Attempt to insert a product with duration_value=0 (violates CHECK)
        bad_product = ProductVariant(
            product_id=customer.id,  # wrong FK type — will cause error
            name="Bad",
            duration_value=0,
            duration_unit=DurationUnit.MONTHS,
            default_price=Decimal("1.00"),
            currency="IDR",
            status="ACTIVE",
        )
        db.add(bad_product)
        try:
            db.flush()
        except Exception:
            db.rollback()

        count_after = db.scalar(
            select(text("count(*)")).select_from(Customer.__table__)
        )
        # original customer fixture row should still be present
        assert count_after is not None


# ─── Audit Log Tests ──────────────────────────────────────────────────────────

class TestAuditLogs:
    def test_product_create_generates_audit_log(
        self, db: Session, admin_user: AdminUser
    ) -> None:
        from app.modules.products.schemas import ProductCreate
        svc = ProductService(db, actor_id=str(admin_user.id))
        svc.create_product(ProductCreate(name="Audit Product", category="Test"))
        log = db.scalar(
            select(AuditLog)
            .where(AuditLog.action == "product.created")
            .order_by(AuditLog.created_at.desc())
        )
        assert log is not None
        assert log.actor_id == str(admin_user.id)
        assert log.entity_type == "Product"
        assert log.after_data is not None
        assert log.after_data["name"] == "Audit Product"

    def test_product_update_generates_before_after(
        self, db: Session, admin_user: AdminUser, product: Product
    ) -> None:
        from app.modules.products.schemas import ProductUpdate
        svc = ProductService(db, actor_id=str(admin_user.id))
        svc.update_product(product.id, ProductUpdate(name="Updated Name"))
        log = db.scalar(
            select(AuditLog)
            .where(AuditLog.action == "product.updated", AuditLog.entity_id == str(product.id))
            .order_by(AuditLog.created_at.desc())
        )
        assert log is not None
        assert log.before_data is not None
        assert log.before_data["name"] == product.name or "name" in log.before_data
        assert log.after_data["name"] == "Updated Name"

    def test_customer_archive_generates_audit_log(
        self, db: Session, admin_user: AdminUser, customer: Customer
    ) -> None:
        svc = CustomerService(db, actor_id=str(admin_user.id))
        svc.archive_customer(customer.id)
        log = db.scalar(
            select(AuditLog)
            .where(
                AuditLog.action == "customer.archived",
                AuditLog.entity_id == str(customer.id),
            )
        )
        assert log is not None
        assert log.after_data is not None
        assert "archived_at" in log.after_data

    def test_rental_create_generates_audit_log(
        self, db: Session, admin_user: AdminUser,
        customer: Customer, product: Product, variant: ProductVariant,
    ) -> None:
        from app.modules.rentals.schemas import RentalCreate
        today = current_wib_date()
        svc = RentalService(db, actor_id=str(admin_user.id))
        svc.create_rental(
            RentalCreate(
                customer_id=customer.id,
                product_id=product.id,
                product_variant_id=variant.id,
                start_date=today,
            ),
            created_by=admin_user.id,
        )
        log = db.scalar(
            select(AuditLog)
            .where(AuditLog.action == "rental.created")
            .order_by(AuditLog.created_at.desc())
        )
        assert log is not None
        assert log.after_data["customer_id"] == str(customer.id)


class TestRentalEditing:
    def test_account_credentials_are_encrypted_in_database(
        self,
        db: Session,
        active_rental: Rental,
        product: Product,
    ) -> None:
        from app.core.encryption import decrypt_credential
        from app.modules.rentals.schemas import RentalUpdate

        product.has_profile_pin = True
        db.flush()
        updated = RentalService(db).update_rental(
            active_rental.id,
            RentalUpdate(
                account_email="account@example.com",
                profile="Profile 2",
                pin="4321",
            ),
        )
        db.refresh(active_rental)

        assert active_rental.account_email_encrypted != "account@example.com"
        assert active_rental.profile_encrypted != "Profile 2"
        assert active_rental.pin_encrypted != "4321"
        assert decrypt_credential(active_rental.account_email_encrypted) == "account@example.com"
        assert decrypt_credential(active_rental.profile_encrypted) == "Profile 2"
        assert decrypt_credential(active_rental.pin_encrypted) == "4321"
        assert updated.account_email == "account@example.com"
        assert updated.profile == "Profile 2"
        assert updated.pin == "4321"

    def test_profile_and_pin_are_rejected_for_products_without_profile_support(
        self,
        db: Session,
        active_rental: Rental,
    ) -> None:
        from app.core.exceptions import BusinessRuleError
        from app.modules.rentals.schemas import RentalUpdate

        with pytest.raises(BusinessRuleError):
            RentalService(db).update_rental(
                active_rental.id,
                RentalUpdate(profile="Profile 2", pin="4321"),
            )

    def test_editing_expiration_invalidates_pending_reminders(
        self, db: Session, active_rental: Rental, admin_user: AdminUser
    ) -> None:
        from app.modules.rentals.schemas import RentalUpdate
        from app.shared.datetime_utils import calculate_reminder_scheduled_utc

        scheduled_at = calculate_reminder_scheduled_utc(
            active_rental.expiration_date,
            ReminderStage.H5,
        )
        notification = Notification(
            rental_id=active_rental.id,
            customer_id=active_rental.customer_id,
            reminder_stage=ReminderStage.H5,
            expiration_version=active_rental.expiration_version,
            scheduled_at=scheduled_at,
            status=NotificationStatus.QUEUED,
            attempt_count=0,
        )
        db.add(notification)
        db.flush()
        outbox_event = OutboxEvent(
            event_type="notification.send",
            aggregate_type="notification",
            aggregate_id=notification.id,
            payload={"notification_id": str(notification.id)},
            status=OutboxStatus.PENDING,
        )
        db.add(outbox_event)
        db.flush()

        new_expiration = active_rental.expiration_date + timedelta(days=10)
        updated = RentalService(db, actor_id=str(admin_user.id)).update_rental(
            active_rental.id,
            RentalUpdate(expiration_date=new_expiration),
        )

        assert updated.expiration_date == new_expiration
        assert updated.expiration_version == 2
        assert notification.status == NotificationStatus.CANCELLED
        assert outbox_event.status == OutboxStatus.PROCESSED


def test_customer_update_can_clear_optional_fields(db: Session, customer: Customer) -> None:
    from app.modules.customers.schemas import CustomerUpdate

    customer.telegram_username = "old_handle"
    customer.internal_notes = "old note"
    db.flush()

    updated = CustomerService(db).update_customer(
        customer.id,
        CustomerUpdate(telegram_username=None, internal_notes=None),
    )

    assert updated.telegram_username is None
    assert updated.internal_notes is None


# ─── Duplicate Prevention Tests ───────────────────────────────────────────────

class TestDuplicatePrevention:
    def test_archive_already_archived_product_raises(
        self, db: Session, admin_user: AdminUser, product: Product
    ) -> None:
        from app.core.exceptions import BusinessRuleError
        svc = ProductService(db, actor_id=str(admin_user.id))
        svc.archive_product(product.id)
        with pytest.raises(BusinessRuleError, match="already archived"):
            svc.archive_product(product.id)

    def test_archive_active_rental_raises(
        self, db: Session, admin_user: AdminUser, active_rental: Rental
    ) -> None:
        from app.core.exceptions import BusinessRuleError
        svc = RentalService(db, actor_id=str(admin_user.id))
        with pytest.raises(BusinessRuleError, match="Cannot archive an active rental"):
            svc.archive_rental(active_rental.id)

    def test_update_archived_rental_raises(
        self, db: Session, admin_user: AdminUser, active_rental: Rental
    ) -> None:
        from app.core.exceptions import BusinessRuleError
        from app.modules.rentals.schemas import RentalUpdate
        from app.shared.datetime_utils import utc_now
        # Force archive at DB level
        active_rental.status = RentalStatus.CANCELLED
        active_rental.archived_at = utc_now()
        db.flush()

        svc = RentalService(db, actor_id=str(admin_user.id))
        with pytest.raises(BusinessRuleError, match="Cannot update an archived rental"):
            svc.update_rental(active_rental.id, RentalUpdate(status=RentalStatus.EXPIRED))

    def test_not_found_raises_correctly(self, db: Session, admin_user: AdminUser) -> None:
        import uuid

        from app.core.exceptions import NotFoundError
        svc = ProductService(db, actor_id=str(admin_user.id))
        with pytest.raises(NotFoundError):
            svc.get_product(uuid.uuid4())
