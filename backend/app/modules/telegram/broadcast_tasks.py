"""Rate-limited background delivery for Telegram broadcasts."""

import asyncio
import logging
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
from celery import shared_task
from sqlalchemy import func, select, update

from app.core.config import settings
from app.db.session import SessionLocal
from app.modules.customers.models import Customer, NotificationConsent
from app.modules.notifications.models import OutboxEvent
from app.modules.telegram.broadcast_service import broadcast_customer_is_eligible, finish_broadcast
from app.modules.telegram.models import TelegramBroadcast, TelegramBroadcastRecipient
from app.shared.datetime_utils import utc_now
from app.shared.enums import (
    ConsentType,
    OutboxStatus,
    TelegramBroadcastDeliveryStatus,
    TelegramBroadcastStatus,
)

logger = logging.getLogger(__name__)
SEND_INTERVAL_SECONDS = 0.2
MAX_RETRY_AFTER_ATTEMPTS = 3
MAX_RETRY_AFTER_WAIT_SECONDS = 60


def _recipient_is_eligible(db, recipient: TelegramBroadcastRecipient) -> bool:
    if recipient.customer_id is None:
        return False
    customer = db.get(Customer, recipient.customer_id)
    if customer is None or customer.telegram_chat_id != recipient.chat_id:
        return False
    consent = db.scalar(
        select(NotificationConsent)
        .where(
            NotificationConsent.customer_id == customer.id,
            NotificationConsent.consent_type == ConsentType.TELEGRAM_REMINDERS,
        )
        .order_by(
            func.coalesce(
                NotificationConsent.revoked_at,
                NotificationConsent.consented_at,
                NotificationConsent.created_at,
            ).desc(),
            NotificationConsent.created_at.desc(),
            NotificationConsent.id.desc(),
        )
        .limit(1)
    )
    return broadcast_customer_is_eligible(customer, consent)


async def _send_to_recipient(
    bot: Bot,
    chat_id: int,
    content_text: str | None,
    media_type: str | None,
    media_file_id: str | None,
) -> tuple[TelegramBroadcastDeliveryStatus, str | None]:
    retry_after_count = 0
    while True:
        try:
            if media_type == "PHOTO":
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=media_file_id or "",
                    caption=content_text,
                )
            elif media_type == "VIDEO":
                await bot.send_video(
                    chat_id=chat_id,
                    video=media_file_id or "",
                    caption=content_text,
                )
            else:
                await bot.send_message(chat_id=chat_id, text=content_text or "")
        except TelegramRetryAfter as exc:
            retry_after_count += 1
            if (
                retry_after_count >= MAX_RETRY_AFTER_ATTEMPTS
                or exc.retry_after > MAX_RETRY_AFTER_WAIT_SECONDS
            ):
                return TelegramBroadcastDeliveryStatus.FAILED, "telegram_retry_after"
            await asyncio.sleep(float(exc.retry_after) + 1)
            continue
        except (
            TelegramBadRequest,
            TelegramForbiddenError,
            TelegramUnauthorizedError,
        ) as exc:
            return TelegramBroadcastDeliveryStatus.FAILED, type(exc).__name__
        except (TelegramNetworkError, TelegramServerError) as exc:
            return TelegramBroadcastDeliveryStatus.AMBIGUOUS, type(exc).__name__
        except TelegramAPIError as exc:
            return TelegramBroadcastDeliveryStatus.AMBIGUOUS, type(exc).__name__
        return TelegramBroadcastDeliveryStatus.SENT, None


def _claim_broadcast(broadcast_id: uuid.UUID) -> int | None:
    with SessionLocal() as db:
        broadcast = db.get(TelegramBroadcast, broadcast_id, with_for_update=True)
        if broadcast is None or broadcast.status not in (
            TelegramBroadcastStatus.QUEUED,
            TelegramBroadcastStatus.SENDING,
        ):
            return None
        if broadcast.status == TelegramBroadcastStatus.SENDING:
            if broadcast.lease_until is not None and broadcast.lease_until > utc_now():
                return None
            db.execute(
                update(TelegramBroadcastRecipient)
                .where(
                    TelegramBroadcastRecipient.broadcast_id == broadcast_id,
                    TelegramBroadcastRecipient.status == TelegramBroadcastDeliveryStatus.SENDING,
                )
                .values(
                    status=TelegramBroadcastDeliveryStatus.AMBIGUOUS,
                    error_code="delivery_uncertain_after_worker_restart",
                )
            )
        broadcast.status = TelegramBroadcastStatus.SENDING
        broadcast.lease_until = utc_now() + timedelta(minutes=5)
        db.commit()
        return broadcast.created_by_telegram_id


async def _dispatch_broadcast(broadcast_id: uuid.UUID) -> dict[str, int | str]:
    claimed = _claim_broadcast(broadcast_id)
    if claimed is None:
        return {"broadcast_id": str(broadcast_id), "status": "not_queued"}
    admin_id = claimed
    async with Bot(token=settings.TELEGRAM_BOT_TOKEN) as bot:
        while True:
            with SessionLocal() as db:
                broadcast = db.get(TelegramBroadcast, broadcast_id)
                if broadcast is None:
                    return {"broadcast_id": str(broadcast_id), "status": "missing"}
                recipient = db.scalar(
                    select(TelegramBroadcastRecipient)
                    .where(
                        TelegramBroadcastRecipient.broadcast_id == broadcast_id,
                        TelegramBroadcastRecipient.status
                        == TelegramBroadcastDeliveryStatus.PENDING,
                    )
                    .order_by(TelegramBroadcastRecipient.id)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
                if recipient is None:
                    counts = dict(
                        db.execute(
                            select(
                                TelegramBroadcastRecipient.status,
                                func.count(),
                            )
                            .where(TelegramBroadcastRecipient.broadcast_id == broadcast_id)
                            .group_by(TelegramBroadcastRecipient.status)
                        ).all()
                    )
                    finish_broadcast(broadcast, counts, utc_now())
                    db.query(TelegramBroadcastRecipient).filter(
                        TelegramBroadcastRecipient.broadcast_id == broadcast_id
                    ).delete(synchronize_session=False)
                    for event in db.scalars(
                        select(OutboxEvent)
                        .where(
                            OutboxEvent.aggregate_type == "telegram_broadcast",
                            OutboxEvent.aggregate_id == broadcast_id,
                            OutboxEvent.status == OutboxStatus.PROCESSING,
                        )
                        .with_for_update()
                    ).all():
                        event.status = OutboxStatus.PROCESSED
                        event.processed_at = broadcast.completed_at
                    db.commit()
                    summary = (
                        f"Broadcast selesai.\n"
                        f"Terkirim: {broadcast.sent_count}\n"
                        f"Gagal: {broadcast.failed_count}\n"
                        f"Dilewati: {broadcast.skipped_count}\n"
                        f"Tidak pasti: {broadcast.ambiguous_count}"
                    )
                    break

                if not _recipient_is_eligible(db, recipient):
                    recipient.status = TelegramBroadcastDeliveryStatus.SKIPPED
                    broadcast.lease_until = utc_now() + timedelta(minutes=5)
                    db.commit()
                    continue
                recipient.status = TelegramBroadcastDeliveryStatus.SENDING
                broadcast.lease_until = utc_now() + timedelta(minutes=5)
                db.commit()
                recipient_id = recipient.id
                chat_id = recipient.chat_id
                content_text = broadcast.content_text
                media_type = broadcast.media_type
                media_file_id = broadcast.media_file_id

            status, error_code = await _send_to_recipient(
                bot,
                chat_id,
                content_text,
                media_type,
                media_file_id,
            )
            with SessionLocal() as db:
                recipient = db.get(TelegramBroadcastRecipient, recipient_id)
                if recipient is not None:
                    recipient.status = status
                    recipient.error_code = error_code
                    recipient.sent_at = (
                        utc_now() if status == TelegramBroadcastDeliveryStatus.SENT else None
                    )
                    broadcast = db.get(TelegramBroadcast, broadcast_id)
                    if broadcast is not None:
                        broadcast.lease_until = utc_now() + timedelta(minutes=5)
                    db.commit()
            await asyncio.sleep(SEND_INTERVAL_SECONDS)

        try:
            await bot.send_message(chat_id=admin_id, text=summary)
        except TelegramAPIError as exc:
            logger.warning(
                "Broadcast %s completed, but its admin summary could not be sent (%s).",
                broadcast_id,
                type(exc).__name__,
            )
    logger.info("Telegram broadcast %s completed for admin %s.", broadcast_id, admin_id)
    return {
        "broadcast_id": str(broadcast_id),
        "status": "completed",
    }


@shared_task(name="telegram.dispatch_broadcast")
def dispatch_telegram_broadcast_task(broadcast_id: str) -> dict[str, int | str]:
    return asyncio.run(_dispatch_broadcast(uuid.UUID(broadcast_id)))
