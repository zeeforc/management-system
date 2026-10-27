"""Business service for scheduling persistent H-5, H-3, and H-1 reminders."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.modules.customers.models import Customer, NotificationConsent
from app.modules.notifications.models import Notification, OutboxEvent
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.schemas import NotificationRead
from app.modules.rentals.repository import RentalRepository
from app.shared.datetime_utils import (
    calculate_reminder_dates,
    calculate_reminder_scheduled_utc,
    current_wib_date,
    utc_now,
)
from app.shared.enums import (
    ConsentStatus,
    ConsentType,
    NotificationStatus,
    OutboxStatus,
    ReminderStage,
)
from app.shared.pagination import PaginatedResponse, PaginationParams


class NotificationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = NotificationRepository(db)
        self.rental_repo = RentalRepository(db)

    def list_notifications(self, params: PaginationParams) -> PaginatedResponse[NotificationRead]:
        items, total = self.repo.list_notifications(params)
        return PaginatedResponse.create(
            items=[
                NotificationRead.model_validate(notification).model_copy(
                    update={
                        "customer_display_name": customer_name,
                        "customer_telegram_username": customer_username,
                        "product_name": product_name,
                        "product_variant_name": variant_name,
                        "expiration_date": expiration_date,
                    }
                )
                for (
                    notification,
                    customer_name,
                    customer_username,
                    product_name,
                    variant_name,
                    expiration_date,
                ) in items
            ],
            total=total,
            params=params,
        )

    def schedule_rental_reminders(self, rental_id: uuid.UUID) -> list[NotificationRead]:
        """Ensure H-5, H-3, and H-1 reminder records exist for the current expiration_version."""
        rental = self.rental_repo.get_rental(rental_id)
        if rental is None:
            raise NotFoundError("Rental", rental_id)

        today = current_wib_date()
        reminder_dates = calculate_reminder_dates(rental.expiration_date)
        existing_by_stage = {
            notification.reminder_stage: notification
            for notification in self.repo.get_for_rental_versions(
                {(rental.id, rental.expiration_version)}
            )
        }
        created_or_existing: list[Notification] = list(existing_by_stage.values())
        for stage in (ReminderStage.H5, ReminderStage.H3, ReminderStage.H1):
            if stage in existing_by_stage:
                continue

            scheduled_at = calculate_reminder_scheduled_utc(
                expiration_date=rental.expiration_date,
                stage=stage,
                send_hour_wib=settings.DEFAULT_REMINDER_SEND_HOUR_WIB,
                send_minute_wib=settings.DEFAULT_REMINDER_SEND_MINUTE_WIB,
            )
            stage_status = (
                NotificationStatus.CANCELLED
                if reminder_dates[stage] < today
                else NotificationStatus.SCHEDULED
            )
            notification = Notification(
                rental_id=rental.id,
                customer_id=rental.customer_id,
                reminder_stage=stage,
                expiration_version=rental.expiration_version,
                scheduled_at=scheduled_at,
                status=stage_status,
                attempt_count=0,
            )
            self.repo.create_notification(notification)
            created_or_existing.append(notification)

        self.db.commit()
        for item in created_or_existing:
            self.db.refresh(item)
        return [NotificationRead.model_validate(item) for item in created_or_existing]

    def scan_due_reminders(self, now: datetime | None = None) -> dict[str, int]:
        """Create due notification/outbox records atomically and reject ineligible recipients."""
        current_time = now or utc_now()
        today = current_wib_date(current_time)
        stages_by_expiration = {
            today + timedelta(days=5): ReminderStage.H5,
            today + timedelta(days=3): ReminderStage.H3,
            today + timedelta(days=1): ReminderStage.H1,
        }
        due_dates = set(stages_by_expiration)
        rentals = self.repo.get_due_rentals(due_dates)
        created_count = 0
        queued_count = 0
        rejected_count = 0
        existing_by_key = {
            (
                notification.rental_id,
                notification.expiration_version,
                notification.reminder_stage,
            ): notification
            for notification in self.repo.get_for_rental_versions(
                {(rental.id, rental.expiration_version) for rental in rentals}
            )
        }
        for rental in rentals:
            stage = stages_by_expiration[rental.expiration_date]
            notification = existing_by_key.get(
                (rental.id, rental.expiration_version, stage)
            )
            if notification is None:
                notification = Notification(
                    rental_id=rental.id,
                    customer_id=rental.customer_id,
                    reminder_stage=stage,
                    expiration_version=rental.expiration_version,
                    scheduled_at=calculate_reminder_scheduled_utc(
                        rental.expiration_date,
                        stage,
                        settings.DEFAULT_REMINDER_SEND_HOUR_WIB,
                        settings.DEFAULT_REMINDER_SEND_MINUTE_WIB,
                    ),
                    status=NotificationStatus.SCHEDULED,
                    attempt_count=0,
                )
                self.repo.create_notification(notification)
                created_count += 1

        due_notifications = self.repo.get_due_notifications(current_time)
        notification_ids = {notification.id for notification in due_notifications}
        rental_by_id = self.rental_repo.get_rentals_for_update(
            {notification.rental_id for notification in due_notifications}
        )
        customer_ids = {notification.customer_id for notification in due_notifications}
        customers_by_id = (
            {
                customer.id: customer
                for customer in self.db.scalars(
                    select(Customer).where(Customer.id.in_(customer_ids))
                ).all()
            }
            if customer_ids
            else {}
        )
        consents_by_customer = {}
        if customer_ids:
            latest_consents = self.db.scalars(
                select(NotificationConsent)
                .where(
                    NotificationConsent.customer_id.in_(customer_ids),
                    NotificationConsent.consent_type == ConsentType.TELEGRAM_REMINDERS,
                )
                .order_by(
                    NotificationConsent.customer_id,
                    func.coalesce(
                        NotificationConsent.revoked_at,
                        NotificationConsent.consented_at,
                        NotificationConsent.created_at,
                    ).desc(),
                    NotificationConsent.created_at.desc(),
                )
            ).all()
            for consent in latest_consents:
                consents_by_customer.setdefault(consent.customer_id, consent)
        pending_outbox_ids = self.repo.get_pending_outbox_notification_ids(notification_ids)

        for notification in due_notifications:
            rental = rental_by_id.get(notification.rental_id)
            customer = customers_by_id.get(notification.customer_id)
            if (
                rental is None
                or rental.archived_at is not None
                or rental.status not in ("ACTIVE", "SCHEDULED")
                or rental.expiration_version != notification.expiration_version
                or rental.expiration_date < today
            ):
                notification.status = NotificationStatus.CANCELLED
                notification.last_error = "Rental is no longer eligible for this reminder."
                rejected_count += 1
                continue

            if (
                customer is None
                or customer.archived_at is not None
                or customer.status != "ACTIVE"
                or customer.telegram_chat_id is None
                or (
                    (consent := consents_by_customer.get(customer.id)) is None
                    or consent.consent_status != ConsentStatus.GRANTED
                )
            ):
                notification.status = NotificationStatus.FAILED_PERMANENT
                notification.last_error = (
                    "Recipient is not linked or has not granted reminder consent."
                )
                rejected_count += 1
                continue

            if notification.id not in pending_outbox_ids:
                self.db.add(
                    OutboxEvent(
                        event_type="notification.send",
                        aggregate_type="notification",
                        aggregate_id=notification.id,
                        payload={"notification_id": str(notification.id)},
                        status=OutboxStatus.PENDING,
                        available_at=current_time,
                    )
                )
            notification.status = NotificationStatus.QUEUED
            queued_count += 1

        self.db.commit()
        return {
            "created": created_count,
            "queued": queued_count,
            "rejected": rejected_count,
        }
