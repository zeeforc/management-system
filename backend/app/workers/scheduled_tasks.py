"""Periodic scheduled scans and durable outbox dispatch."""

import logging
from datetime import timedelta

from app.db.session import SessionLocal
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.service import NotificationService
from app.modules.notifications.tasks import dispatch_reminder_task
from app.shared.datetime_utils import utc_now
from app.shared.enums import NotificationStatus, OutboxStatus
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="scheduler.scan_upcoming_reminders")
def scan_upcoming_reminders() -> dict[str, int]:
    """Create due reminder records and outbox entries in a single database transaction."""
    with SessionLocal() as db:
        result = NotificationService(db).scan_due_reminders()
    logger.info(
        "Reminder scan created=%d queued=%d rejected=%d",
        result["created"],
        result["queued"],
        result["rejected"],
    )
    return result


@celery_app.task(name="scheduler.process_outbox_events")
def process_outbox_events() -> dict[str, int]:
    """Dispatch outbox records with a recoverable five-minute claim lease."""
    dispatched = 0
    with SessionLocal() as db:
        repository = NotificationRepository(db)
        events = repository.get_due_outbox_events(utc_now())
        lease_until = utc_now() + timedelta(minutes=5)
        for event in events:
            event.status = OutboxStatus.PROCESSING
            event.available_at = lease_until
        db.commit()

        for event in events:
            notification_id = event.payload.get("notification_id")
            if event.aggregate_type != "notification" or not notification_id:
                event.status = OutboxStatus.FAILED
                event.last_error = "Unsupported or malformed notification outbox event."
                event.processed_at = utc_now()
                db.commit()
                continue

            notification = repository.get_notification(event.aggregate_id)
            if notification is None or str(notification.id) != str(notification_id):
                event.status = OutboxStatus.FAILED
                event.last_error = "Notification outbox reference does not match a notification."
                event.processed_at = utc_now()
                db.commit()
                continue

            if notification.status in (
                NotificationStatus.QUEUED,
                NotificationStatus.FAILED_RETRYABLE,
            ):
                dispatch_reminder_task.apply_async(args=[str(notification_id)])
                event.last_error = None
                dispatched += 1
            else:
                event.status = OutboxStatus.PROCESSED
                event.processed_at = utc_now()
            db.commit()

    return {"dispatched": dispatched}
