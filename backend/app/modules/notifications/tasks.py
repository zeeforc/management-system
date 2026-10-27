"""Celery tasks for reliable Telegram reminder delivery."""

import asyncio
import logging
import random
import uuid
from datetime import timedelta

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
    TelegramUnauthorizedError,
)
from aiogram.types import InlineKeyboardMarkup
from celery import shared_task
from sqlalchemy import select

from app.core.config import settings
from app.core.exceptions import BusinessRuleError
from app.db.session import SessionLocal
from app.modules.notifications.delivery import (
    build_admin_reminder_message,
    build_reminder_message,
)
from app.modules.notifications.models import Notification, NotificationAttempt, OutboxEvent
from app.modules.rentals.models import Rental
from app.shared.datetime_utils import current_wib_date, utc_now
from app.shared.enums import (
    AttemptResultStatus,
    NotificationStatus,
    OutboxStatus,
)

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3
RETRY_BASE_SECONDS = 60
RETRY_MAX_SECONDS = 3600


async def _send_message(
    chat_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None,
) -> int:
    async with Bot(token=settings.TELEGRAM_BOT_TOKEN) as bot:
        message = await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    return message.message_id


async def _send_admin_reminders(text: str) -> None:
    if not settings.TELEGRAM_ADMIN_USER_IDS:
        return
    try:
        async with Bot(token=settings.TELEGRAM_BOT_TOKEN) as bot:
            for admin_id in settings.TELEGRAM_ADMIN_USER_IDS:
                try:
                    await bot.send_message(
                        chat_id=admin_id,
                        text=text,
                        parse_mode="HTML",
                    )
                except TelegramAPIError as exc:
                    logger.warning(
                        "Could not deliver sensitive reminder details to Telegram admin %s (%s). "
                        "The customer reminder delivery will continue.",
                        admin_id,
                        type(exc).__name__,
                    )
    except TelegramAPIError as exc:
        logger.warning(
            "Could not initialize Telegram delivery for admin reminder details (%s). "
            "The customer reminder delivery will continue.",
            type(exc).__name__,
        )


def _finish_attempt(
    notification_id: uuid.UUID,
    attempt_id: uuid.UUID,
    result_status: AttemptResultStatus,
    *,
    message_id: int | None = None,
    error_code: str | None = None,
    error_summary: str | None = None,
    retry_delay: int | None = None,
) -> str:
    with SessionLocal() as db:
        notification = db.get(Notification, notification_id)
        attempt = db.get(NotificationAttempt, attempt_id)
        if notification is None or attempt is None:
            raise RuntimeError("Notification or attempt disappeared while processing delivery.")

        attempt.finished_at = utc_now()
        attempt.result_status = result_status
        attempt.telegram_message_id = message_id
        attempt.error_code = error_code
        attempt.error_summary = error_summary[:1000] if error_summary else None
        notification.last_error = error_summary[:1000] if error_summary else None
        for event in db.scalars(
            select(OutboxEvent)
            .where(
                OutboxEvent.aggregate_type == "notification",
                OutboxEvent.aggregate_id == notification.id,
                OutboxEvent.status == OutboxStatus.PROCESSING,
            )
            .with_for_update()
        ).all():
            event.status = OutboxStatus.PROCESSED
            event.processed_at = attempt.finished_at

        if result_status == AttemptResultStatus.SUCCESS:
            notification.status = NotificationStatus.SENT
            notification.sent_at = attempt.finished_at
            notification.telegram_message_id = message_id
        elif result_status == AttemptResultStatus.FAILED_RETRYABLE:
            if notification.attempt_count >= MAX_ATTEMPTS:
                notification.status = NotificationStatus.FAILED_PERMANENT
                attempt.result_status = AttemptResultStatus.FAILED_PERMANENT
            else:
                notification.status = NotificationStatus.FAILED_RETRYABLE
                delay = retry_delay or min(
                    RETRY_BASE_SECONDS * (2 ** (notification.attempt_count - 1))
                    + random.randint(0, RETRY_BASE_SECONDS),
                    RETRY_MAX_SECONDS,
                )
                db.add(
                    OutboxEvent(
                        event_type="notification.retry",
                        aggregate_type="notification",
                        aggregate_id=notification.id,
                        payload={"notification_id": str(notification.id)},
                        status=OutboxStatus.PENDING,
                        available_at=utc_now() + timedelta(seconds=delay),
                    )
                )
        elif result_status == AttemptResultStatus.FAILED_PERMANENT:
            notification.status = NotificationStatus.FAILED_PERMANENT
        else:
            notification.status = NotificationStatus.AMBIGUOUS

        db.commit()
        return str(notification.status)


@shared_task(name="notifications.dispatch_reminder")
def dispatch_reminder_task(notification_id: str) -> dict[str, str]:
    """Revalidate eligibility, persist an attempt, then send one Telegram reminder."""
    identifier = uuid.UUID(notification_id)
    with SessionLocal() as db:
        notification = db.get(Notification, identifier, with_for_update=True)
        if notification is None:
            return {"notification_id": notification_id, "status": "missing"}
        if notification.status not in (
            NotificationStatus.QUEUED,
            NotificationStatus.FAILED_RETRYABLE,
        ):
            return {"notification_id": notification_id, "status": str(notification.status)}

        try:
            chat_id, text, keyboard = build_reminder_message(db, identifier)
            admin_text = (
                build_admin_reminder_message(db, identifier)
                if settings.TELEGRAM_ADMIN_USER_IDS
                else None
            )
        except BusinessRuleError as exc:
            rental = db.get(Rental, notification.rental_id)
            if (
                rental is None
                or rental.archived_at is not None
                or rental.status not in ("ACTIVE", "SCHEDULED")
                or rental.expiration_version != notification.expiration_version
                or rental.expiration_date < current_wib_date()
            ):
                notification.status = NotificationStatus.CANCELLED
            else:
                notification.status = NotificationStatus.FAILED_PERMANENT
            notification.last_error = str(exc)
            for event in db.scalars(
                select(OutboxEvent)
                .where(
                    OutboxEvent.aggregate_type == "notification",
                    OutboxEvent.aggregate_id == notification.id,
                    OutboxEvent.status == OutboxStatus.PROCESSING,
                )
                .with_for_update()
            ).all():
                event.status = OutboxStatus.PROCESSED
                event.processed_at = utc_now()
            db.commit()
            return {"notification_id": notification_id, "status": "ineligible"}

        attempt = NotificationAttempt(
            notification_id=identifier,
            attempt_number=notification.attempt_count + 1,
            started_at=utc_now(),
            result_status=AttemptResultStatus.AMBIGUOUS,
        )
        notification.attempt_count += 1
        notification.status = NotificationStatus.AMBIGUOUS
        notification.last_error = None
        db.add(attempt)
        db.commit()
        attempt_id = attempt.id

    try:
        message_id = asyncio.run(_send_message(chat_id, text, keyboard))
    except TelegramRetryAfter as exc:
        status = _finish_attempt(
            identifier,
            attempt_id,
            AttemptResultStatus.FAILED_RETRYABLE,
            error_code="telegram_retry_after",
            error_summary=str(exc),
            retry_delay=int(exc.retry_after) + 1,
        )
        task_status = (
            "retry_scheduled" if status == NotificationStatus.FAILED_RETRYABLE else status.lower()
        )
        return {"notification_id": notification_id, "status": task_status}
    except (
        TelegramBadRequest,
        TelegramForbiddenError,
        TelegramUnauthorizedError,
    ) as exc:
        _finish_attempt(
            identifier,
            attempt_id,
            AttemptResultStatus.FAILED_PERMANENT,
            error_code=type(exc).__name__,
            error_summary=str(exc),
        )
        return {"notification_id": notification_id, "status": "failed_permanent"}
    except (TelegramNetworkError, TelegramServerError) as exc:
        logger.exception("Telegram reminder delivery outcome is uncertain for %s", identifier)
        _finish_attempt(
            identifier,
            attempt_id,
            AttemptResultStatus.AMBIGUOUS,
            error_code=type(exc).__name__,
            error_summary=str(exc),
        )
        return {"notification_id": notification_id, "status": "ambiguous"}
    except TelegramAPIError as exc:
        _finish_attempt(
            identifier,
            attempt_id,
            AttemptResultStatus.AMBIGUOUS,
            error_code=type(exc).__name__,
            error_summary=str(exc),
        )
        return {"notification_id": notification_id, "status": "ambiguous"}

    _finish_attempt(
        identifier,
        attempt_id,
        AttemptResultStatus.SUCCESS,
        message_id=message_id,
    )
    if admin_text is not None:
        asyncio.run(_send_admin_reminders(admin_text))
    return {"notification_id": notification_id, "status": "sent"}
