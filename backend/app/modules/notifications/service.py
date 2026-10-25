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
            items=[NotificationRead.model_validate(item) for item in items],
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
        created_or_existing: list[Notification] = []
        for stage in (ReminderStage.H5, ReminderStage.H3, ReminderStage.H1):
            existing = self.repo.get_by_rental_version_stage(
                rental_id=rental.id,
                expiration_version=rental.expiration_version,
                reminder_stage=stage.value,
            )
            if existing is not None:
                created_or_existing.append(existing)
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
        for rental in rentals:
            stage = stages_by_expiration[rental.expiration_date]
            notification = self.repo.get_by_rental_version_stage(
                rental.id,
                rental.expiration_version,
                stage.value,
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
        for notification in due_notifications:
            rental = self.rental_repo.get_rental(notification.rental_id, for_update=True)
            customer = self.db.get(Customer, notification.customer_id)
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
                or not self._has_granted_consent(
                    customer.id,
                    ConsentType.TELEGRAM_REMINDERS,
                )
            ):
                notification.status = NotificationStatus.FAILED_PERMANENT
                notification.last_error = (
                    "Recipient is not linked or has not granted reminder consent."
                )
                rejected_count += 1
                continue

            if not self.repo.has_pending_outbox_event(notification.id):
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

    def _has_granted_consent(self, customer_id: uuid.UUID, consent_type: ConsentType) -> bool:
        consent = self.db.scalar(
            select(NotificationConsent)
            .where(
                NotificationConsent.customer_id == customer_id,
                NotificationConsent.consent_type == consent_type,
            )
            .order_by(
                func.coalesce(
                    NotificationConsent.revoked_at,
                    NotificationConsent.consented_at,
                    NotificationConsent.created_at,
                ).desc(),
                NotificationConsent.created_at.desc(),
            )
            .limit(1)
        )
        return consent is not None and consent.consent_status == ConsentStatus.GRANTED
