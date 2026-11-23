"""Database operations for confirmed, consent-aware Telegram broadcasts."""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError
from app.modules.audit.models import AuditLog
from app.modules.customers.models import Customer, NotificationConsent
from app.modules.notifications.models import OutboxEvent
from app.modules.telegram.models import TelegramBroadcast, TelegramBroadcastRecipient
from app.shared.datetime_utils import utc_now
from app.shared.enums import (
    ActorType,
    ConsentStatus,
    ConsentType,
    CustomerStatus,
    OutboxStatus,
    TelegramBroadcastDeliveryStatus,
    TelegramBroadcastStatus,
)

MAX_BROADCAST_TEXT_LENGTH = 4096
MAX_BROADCAST_CAPTION_LENGTH = 1024


@dataclass(frozen=True)
class TelegramBroadcastPreview:
    broadcast_id: uuid.UUID
    content_text: str | None
    media_type: str | None
    media_file_id: str | None
    recipient_count: int


def validate_broadcast_content(
    content_text: str | None,
    media_type: str | None,
    media_file_id: str | None,
) -> tuple[str | None, str | None, str | None]:
    normalized_text = content_text if content_text and content_text.strip() else None
    if normalized_text is None and media_type is None:
        raise BusinessRuleError("Isi broadcast berupa teks, foto, atau video.")
    if media_type not in (None, "PHOTO", "VIDEO"):
        raise BusinessRuleError("Broadcast hanya mendukung teks, foto, dan video.")
    if media_type is None and media_file_id is not None:
        raise BusinessRuleError("File media broadcast tidak sesuai.")
    if media_type is not None and not media_file_id:
        raise BusinessRuleError("Media broadcast tidak valid. Kirim ulang foto atau videonya.")
    max_length = MAX_BROADCAST_CAPTION_LENGTH if media_type else MAX_BROADCAST_TEXT_LENGTH
    if normalized_text is not None and len(normalized_text) > max_length:
        label = "Caption media" if media_type else "Teks broadcast"
        raise BusinessRuleError(f"{label} maksimal {max_length} karakter.")
    return normalized_text, media_type, media_file_id


def broadcast_customer_is_eligible(
    customer: Customer,
    latest_consent: NotificationConsent | None,
) -> bool:
    return (
        customer.status == CustomerStatus.ACTIVE
        and customer.archived_at is None
        and customer.telegram_chat_id is not None
        and latest_consent is not None
        and latest_consent.consent_status == ConsentStatus.GRANTED
    )


def finish_broadcast(
    broadcast: TelegramBroadcast,
    delivery_counts: dict[TelegramBroadcastDeliveryStatus, int],
    completed_at: datetime,
) -> None:
    broadcast.sent_count = delivery_counts.get(TelegramBroadcastDeliveryStatus.SENT, 0)
    broadcast.failed_count = delivery_counts.get(TelegramBroadcastDeliveryStatus.FAILED, 0)
    broadcast.skipped_count = delivery_counts.get(TelegramBroadcastDeliveryStatus.SKIPPED, 0)
    broadcast.ambiguous_count = delivery_counts.get(
        TelegramBroadcastDeliveryStatus.AMBIGUOUS,
        0,
    )
    broadcast.status = TelegramBroadcastStatus.COMPLETED
    broadcast.content_text = None
    broadcast.media_type = None
    broadcast.media_file_id = None
    broadcast.lease_until = None
    broadcast.completed_at = completed_at


class TelegramBroadcastService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_draft(
        self,
        telegram_admin_id: int,
        content_text: str | None,
        media_type: str | None,
        media_file_id: str | None,
    ) -> TelegramBroadcastPreview:
        content_text, media_type, media_file_id = validate_broadcast_content(
            content_text,
            media_type,
            media_file_id,
        )
        customers = list(
            self.db.scalars(
                select(Customer)
                .where(
                    Customer.status == CustomerStatus.ACTIVE,
                    Customer.archived_at.is_(None),
                    Customer.telegram_chat_id.is_not(None),
                )
                .order_by(Customer.id)
            ).all()
        )
        if not customers:
            raise BusinessRuleError("Belum ada customer aktif yang sudah menautkan Telegram.")

        customer_ids = [customer.id for customer in customers]
        consents = self.db.scalars(
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
                NotificationConsent.id.desc(),
            )
        ).all()
        latest_consents = latest_consent_by_customer(consents)
        recipients = [
            customer
            for customer in customers
            if broadcast_customer_is_eligible(customer, latest_consents.get(customer.id))
        ]
        if not recipients:
            raise BusinessRuleError("Tidak ada customer aktif yang menyetujui pesan Telegram.")

        broadcast = TelegramBroadcast(
            created_by_telegram_id=telegram_admin_id,
            status=TelegramBroadcastStatus.DRAFT,
            content_text=content_text,
            media_type=media_type,
            media_file_id=media_file_id,
            recipient_count=len(recipients),
        )
        self.db.add(broadcast)
        self.db.flush()
        self.db.add_all(
            [
                TelegramBroadcastRecipient(
                    broadcast_id=broadcast.id,
                    customer_id=customer.id,
                    chat_id=customer.telegram_chat_id,
                )
                for customer in recipients
            ]
        )
        self.db.add(
            AuditLog(
                actor_type=ActorType.ADMIN,
                actor_id=str(telegram_admin_id),
                action="telegram.broadcast_created",
                entity_type="TelegramBroadcast",
                entity_id=str(broadcast.id),
                after_data={
                    "recipient_count": len(recipients),
                    "media_type": media_type,
                },
            )
        )
        self.db.commit()
        return TelegramBroadcastPreview(
            broadcast_id=broadcast.id,
            content_text=content_text,
            media_type=media_type,
            media_file_id=media_file_id,
            recipient_count=len(recipients),
        )

    def confirm(self, broadcast_id: uuid.UUID, telegram_admin_id: int) -> tuple[bool, int]:
        broadcast = self.db.get(TelegramBroadcast, broadcast_id, with_for_update=True)
        if broadcast is None or broadcast.created_by_telegram_id != telegram_admin_id:
            raise BusinessRuleError("Draft broadcast tidak ditemukan.")
        if broadcast.status != TelegramBroadcastStatus.DRAFT:
            return False, broadcast.recipient_count
        broadcast.status = TelegramBroadcastStatus.QUEUED
        recipient_count = broadcast.recipient_count
        self.db.add(
            OutboxEvent(
                event_type="telegram.broadcast",
                aggregate_type="telegram_broadcast",
                aggregate_id=broadcast.id,
                payload={"broadcast_id": str(broadcast.id)},
                status=OutboxStatus.PENDING,
            )
        )
        self.db.commit()
        return True, recipient_count

    def cancel(self, broadcast_id: uuid.UUID, telegram_admin_id: int) -> None:
        broadcast = self.db.get(TelegramBroadcast, broadcast_id, with_for_update=True)
        if broadcast is None or broadcast.created_by_telegram_id != telegram_admin_id:
            raise BusinessRuleError("Draft broadcast tidak ditemukan.")
        if broadcast.status != TelegramBroadcastStatus.DRAFT:
            raise BusinessRuleError("Broadcast yang sudah masuk antrean tidak dapat dibatalkan.")
        self.db.query(TelegramBroadcastRecipient).filter(
            TelegramBroadcastRecipient.broadcast_id == broadcast.id
        ).delete(synchronize_session=False)
        broadcast.status = TelegramBroadcastStatus.CANCELLED
        broadcast.content_text = None
        broadcast.media_type = None
        broadcast.media_file_id = None
        broadcast.completed_at = utc_now()
        self.db.commit()


def latest_consent_by_customer(
    consents: Iterable[NotificationConsent],
) -> dict[uuid.UUID, NotificationConsent]:
    latest: dict[uuid.UUID, NotificationConsent] = {}
    for consent in consents:
        latest.setdefault(consent.customer_id, consent)
    return latest
