"""Business service for rental creation and derived status evaluation."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.encryption import decrypt_credential, encrypt_credential
from app.core.exceptions import BusinessRuleError, NotFoundError
from app.modules.audit.models import AuditLog
from app.modules.customers.repository import CustomerRepository
from app.modules.notifications.models import Notification, OutboxEvent
from app.modules.products.repository import ProductRepository
from app.modules.rentals.models import Rental
from app.modules.rentals.repository import RentalRepository
from app.modules.rentals.schemas import RentalCreate, RentalRead, RentalUpdate
from app.shared.datetime_utils import (
    calculate_expiration_date,
    current_wib_date,
    days_until_expiration,
    derive_effective_rental_status,
    derive_expiration_warning_state,
    utc_now,
)
from app.shared.enums import ActorType, NotificationStatus, OutboxStatus, RentalStatus
from app.shared.money import normalize_money, validate_currency
from app.shared.pagination import PaginatedResponse, PaginationParams


class RentalService:
    def __init__(self, db: Session, actor_id: str | None = None) -> None:
        self.db = db
        self.repo = RentalRepository(db)
        self.customer_repo = CustomerRepository(db)
        self.product_repo = ProductRepository(db)
        self.actor_id = actor_id

    def _audit(self, action: str, entity_id: str, before: dict | None, after: dict | None) -> None:
        log = AuditLog(
            actor_type=ActorType.ADMIN,
            actor_id=self.actor_id,
            action=action,
            entity_type="Rental",
            entity_id=entity_id,
            before_data=before,
            after_data=after,
        )
        self.db.add(log)

    @staticmethod
    def to_read_schema(rental: Rental) -> RentalRead:
        today = current_wib_date()
        effective_status = derive_effective_rental_status(
            stored_status=rental.status,
            start_date=rental.start_date,
            expiration_date=rental.expiration_date,
            wib_today=today,
        )
        warning_state = derive_expiration_warning_state(
            lifecycle_status=rental.status,
            expiration_date=rental.expiration_date,
            wib_today=today,
        )
        remaining = days_until_expiration(rental.expiration_date, wib_today=today)
        return RentalRead(
            id=rental.id,
            customer_id=rental.customer_id,
            product_id=rental.product_id,
            product_variant_id=rental.product_variant_id,
            start_date=rental.start_date,
            expiration_date=rental.expiration_date,
            expiration_version=rental.expiration_version,
            duration_value=rental.duration_value,
            duration_unit=rental.duration_unit,
            agreed_price=rental.agreed_price,
            currency=rental.currency,
            account_email=decrypt_credential(rental.account_email_encrypted),
            profile=decrypt_credential(rental.profile_encrypted),
            pin=decrypt_credential(rental.pin_encrypted),
            status=rental.status,
            effective_status=effective_status,
            warning_state=warning_state,
            days_remaining=remaining,
            renewal_model=rental.renewal_model,
            created_by=rental.created_by,
            created_at=rental.created_at,
            updated_at=rental.updated_at,
            archived_at=rental.archived_at,
        )

    def list_rentals(self, params: PaginationParams) -> PaginatedResponse[RentalRead]:
        items, total = self.repo.list_rentals(params)
        return PaginatedResponse.create(
            items=[
                self.to_read_schema(rental).model_copy(
                    update={
                        "customer_display_name": customer_name,
                        "product_name": product_name,
                        "product_variant_name": variant_name,
                    }
                )
                for rental, customer_name, product_name, variant_name in items
            ],
            total=total,
            params=params,
        )

    def get_rental(self, rental_id: uuid.UUID) -> RentalRead:
        rental = self.repo.get_rental(rental_id)
        if rental is None:
            raise NotFoundError("Rental", rental_id)
        return self.to_read_schema(rental)

    def create_rental(
        self,
        payload: RentalCreate,
        created_by: uuid.UUID | None = None,
    ) -> RentalRead:
        customer = self.customer_repo.get_customer(payload.customer_id)
        if customer is None:
            raise NotFoundError("Customer", payload.customer_id)

        product = self.product_repo.get_product(payload.product_id)
        if product is None:
            raise NotFoundError("Product", payload.product_id)

        variant = self.product_repo.get_variant(payload.product_variant_id)
        if variant is None or variant.product_id != product.id:
            raise BusinessRuleError("Selected variant does not belong to the specified product.")
        if not product.has_profile_pin and any(
            value and value.strip() for value in (payload.profile, payload.pin)
        ):
            raise BusinessRuleError(
                "Profile and PIN are only available for products configured with profile/PIN."
            )

        duration_value = payload.duration_value or variant.duration_value
        duration_unit = payload.duration_unit or variant.duration_unit
        expiration_date = payload.expiration_date or calculate_expiration_date(
            start_date=payload.start_date,
            duration_value=duration_value,
            duration_unit=duration_unit,
        )
        if expiration_date < payload.start_date:
            raise BusinessRuleError("expiration_date must be greater than or equal to start_date.")

        currency = validate_currency(payload.currency or variant.currency)
        raw_price = (
            payload.agreed_price
            if payload.agreed_price is not None
            else variant.default_price
        )
        agreed_price = normalize_money(raw_price, currency)

        today = current_wib_date()
        initial_status = (
            RentalStatus.SCHEDULED if payload.start_date > today else RentalStatus.ACTIVE
        )

        rental = Rental(
            customer_id=customer.id,
            product_id=product.id,
            product_variant_id=variant.id,
            start_date=payload.start_date,
            expiration_date=expiration_date,
            expiration_version=1,
            duration_value=duration_value,
            duration_unit=duration_unit,
            agreed_price=agreed_price,
            currency=currency,
            account_email_encrypted=encrypt_credential(payload.account_email),
            profile_encrypted=encrypt_credential(payload.profile),
            pin_encrypted=encrypt_credential(payload.pin),
            status=initial_status,
            renewal_model=payload.renewal_model,
            created_by=created_by,
        )
        self.repo.create_rental(rental)
        self._audit(
            "rental.created",
            str(rental.id),
            None,
            {
                "customer_id": str(rental.customer_id),
                "expiration_date": str(rental.expiration_date),
                "agreed_price": str(rental.agreed_price),
            },
        )
        self.db.commit()
        self.db.refresh(rental)
        return self.to_read_schema(rental)

    def update_rental(self, rental_id: uuid.UUID, payload: RentalUpdate) -> RentalRead:
        rental = self.repo.get_rental(rental_id, for_update=True)
        if rental is None:
            raise NotFoundError("Rental", rental_id)
        if rental.archived_at is not None:
            raise BusinessRuleError("Cannot update an archived rental.")
        before = {
            "customer_id": str(rental.customer_id),
            "product_id": str(rental.product_id),
            "product_variant_id": str(rental.product_variant_id),
            "start_date": str(rental.start_date),
            "expiration_date": str(rental.expiration_date),
            "duration_value": rental.duration_value,
            "duration_unit": str(rental.duration_unit),
            "agreed_price": str(rental.agreed_price),
            "currency": rental.currency,
            "status": str(rental.status),
            "renewal_model": str(rental.renewal_model),
        }
        previous_customer_id = rental.customer_id
        previous_start_date = rental.start_date
        previous_expiration_date = rental.expiration_date
        previous_status = rental.status

        customer_id = payload.customer_id or rental.customer_id
        customer = self.customer_repo.get_customer(customer_id)
        if customer is None or customer.archived_at is not None:
            raise NotFoundError("Active Customer", customer_id)

        product_id = payload.product_id or rental.product_id
        product = self.product_repo.get_product(product_id)
        if product is None or product.archived_at is not None:
            raise NotFoundError("Active Product", product_id)

        variant_id = payload.product_variant_id or rental.product_variant_id
        variant = self.product_repo.get_variant(variant_id)
        if variant is None or variant.archived_at is not None or variant.product_id != product.id:
            raise BusinessRuleError("Selected variant must belong to the selected active product.")
        if not product.has_profile_pin and any(
            value and value.strip()
            for value in (
                payload.profile if "profile" in payload.model_fields_set else None,
                payload.pin if "pin" in payload.model_fields_set else None,
            )
        ):
            raise BusinessRuleError(
                "Profile and PIN are only available for products configured with profile/PIN."
            )
        variant_changed = variant.id != rental.product_variant_id

        start_date = payload.start_date or rental.start_date
        duration_value = payload.duration_value or rental.duration_value
        duration_unit = payload.duration_unit or rental.duration_unit
        if variant_changed and payload.duration_value is None:
            duration_value = variant.duration_value
        if variant_changed and payload.duration_unit is None:
            duration_unit = variant.duration_unit
        expiration_date = payload.expiration_date
        if expiration_date is None:
            if (
                variant_changed
                or payload.start_date is not None
                or payload.duration_value is not None
                or payload.duration_unit is not None
            ):
                expiration_date = calculate_expiration_date(
                    start_date,
                    duration_value,
                    duration_unit,
                )
            else:
                expiration_date = rental.expiration_date
        if expiration_date < start_date:
            raise BusinessRuleError("expiration_date must be greater than or equal to start_date.")

        currency = validate_currency(payload.currency or rental.currency)
        agreed_price = (
            normalize_money(payload.agreed_price, currency)
            if payload.agreed_price is not None
            else rental.agreed_price
        )
        if variant_changed and payload.agreed_price is None:
            currency = validate_currency(variant.currency)
            agreed_price = normalize_money(variant.default_price, currency)

        rental.customer_id = customer.id
        rental.product_id = product.id
        rental.product_variant_id = variant.id
        rental.start_date = start_date
        rental.expiration_date = expiration_date
        rental.duration_value = duration_value
        rental.duration_unit = duration_unit
        rental.currency = currency
        rental.agreed_price = agreed_price
        if "account_email" in payload.model_fields_set:
            rental.account_email_encrypted = encrypt_credential(payload.account_email)
        if "profile" in payload.model_fields_set:
            rental.profile_encrypted = encrypt_credential(payload.profile)
        if "pin" in payload.model_fields_set:
            rental.pin_encrypted = encrypt_credential(payload.pin)

        if payload.status is not None:
            if payload.status == RentalStatus.CANCELLED and rental.status in (
                RentalStatus.EXPIRED,
                RentalStatus.CANCELLED,
            ):
                raise BusinessRuleError(
                    f"Cannot transition rental status from {rental.status} "
                    f"to {payload.status}."
                )
            rental.status = payload.status
        if payload.renewal_model is not None:
            rental.renewal_model = payload.renewal_model

        changed_for_reminders = any(
            (
                previous_customer_id != rental.customer_id,
                previous_start_date != rental.start_date,
                previous_expiration_date != rental.expiration_date,
                previous_status != rental.status,
            )
        )
        if changed_for_reminders:
            rental.expiration_version += 1
            pending_notifications = self.db.scalars(
                select(Notification).where(
                    Notification.rental_id == rental.id,
                    Notification.status.in_(
                        (
                            NotificationStatus.SCHEDULED,
                            NotificationStatus.QUEUED,
                            NotificationStatus.FAILED_RETRYABLE,
                        )
                    ),
                )
            ).all()
            for notification in pending_notifications:
                notification.status = NotificationStatus.CANCELLED
                notification.last_error = "Rental was edited; this reminder is no longer current."
            notification_ids = {notification.id for notification in pending_notifications}
            if notification_ids:
                pending_events = self.db.scalars(
                    select(OutboxEvent).where(
                        OutboxEvent.aggregate_type == "notification",
                        OutboxEvent.aggregate_id.in_(notification_ids),
                        OutboxEvent.status.in_((OutboxStatus.PENDING, OutboxStatus.PROCESSING)),
                    )
                ).all()
                for event in pending_events:
                    event.status = OutboxStatus.PROCESSED
                    event.processed_at = utc_now()

        after = {
            "customer_id": str(rental.customer_id),
            "product_id": str(rental.product_id),
            "product_variant_id": str(rental.product_variant_id),
            "start_date": str(rental.start_date),
            "expiration_date": str(rental.expiration_date),
            "duration_value": rental.duration_value,
            "duration_unit": str(rental.duration_unit),
            "agreed_price": str(rental.agreed_price),
            "currency": rental.currency,
            "status": str(rental.status),
            "renewal_model": str(rental.renewal_model),
        }
        self._audit(
            "rental.updated",
            str(rental.id),
            before,
            after,
        )
        self.db.commit()
        self.db.refresh(rental)
        return self.to_read_schema(rental)

    def archive_rental(self, rental_id: uuid.UUID) -> RentalRead:
        rental = self.repo.get_rental(rental_id, for_update=True)
        if rental is None:
            raise NotFoundError("Rental", rental_id)
        if rental.archived_at is not None:
            raise BusinessRuleError("Rental is already archived.")
        if rental.status == RentalStatus.ACTIVE:
            raise BusinessRuleError("Cannot archive an active rental. Cancel it first.")
        before = {"archived_at": None, "status": rental.status}
        rental.archived_at = utc_now()
        self._audit(
            "rental.archived",
            str(rental.id),
            before,
            {"archived_at": str(rental.archived_at)},
        )
        self.db.commit()
        self.db.refresh(rental)
        return self.to_read_schema(rental)
