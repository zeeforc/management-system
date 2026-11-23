import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError
from app.modules.customers.models import Customer, NotificationConsent
from app.modules.notifications.models import OutboxEvent
from app.modules.telegram.broadcast_service import (
    MAX_BROADCAST_CAPTION_LENGTH,
    MAX_BROADCAST_TEXT_LENGTH,
    TelegramBroadcastService,
    broadcast_customer_is_eligible,
    finish_broadcast,
    latest_consent_by_customer,
    validate_broadcast_content,
)
from app.modules.telegram.broadcast_tasks import _send_to_recipient
from app.modules.telegram.models import TelegramBroadcast
from app.shared.datetime_utils import utc_now
from app.shared.enums import (
    ConsentStatus,
    ConsentType,
    CustomerStatus,
    OutboxStatus,
    TelegramBroadcastDeliveryStatus,
    TelegramBroadcastStatus,
)


@pytest.mark.parametrize(
    ("content_text", "media_type", "media_file_id"),
    [
        ("Pengumuman toko", None, None),
        ("Info foto", "PHOTO", "telegram-photo-file-id"),
        ("Info video", "VIDEO", "telegram-video-file-id"),
    ],
)
def test_validate_supported_broadcast_content(
    content_text: str,
    media_type: str | None,
    media_file_id: str | None,
) -> None:
    assert validate_broadcast_content(content_text, media_type, media_file_id) == (
        content_text,
        media_type,
        media_file_id,
    )


def test_validate_broadcast_content_rejects_empty_unsupported_and_oversized_content() -> None:
    with pytest.raises(BusinessRuleError, match="Isi broadcast"):
        validate_broadcast_content("  ", None, None)
    with pytest.raises(BusinessRuleError, match="hanya mendukung"):
        validate_broadcast_content("Dokumen", "DOCUMENT", "file-id")
    with pytest.raises(BusinessRuleError, match=str(MAX_BROADCAST_TEXT_LENGTH)):
        validate_broadcast_content("x" * (MAX_BROADCAST_TEXT_LENGTH + 1), None, None)
    with pytest.raises(BusinessRuleError, match=str(MAX_BROADCAST_CAPTION_LENGTH)):
        validate_broadcast_content(
            "x" * (MAX_BROADCAST_CAPTION_LENGTH + 1),
            "PHOTO",
            "photo-file-id",
        )


def test_latest_consent_selection_keeps_most_recent_record_per_customer() -> None:
    customer_id = uuid.uuid4()
    latest = SimpleNamespace(
        customer_id=customer_id,
        consent_status=ConsentStatus.REVOKED,
    )
    older = SimpleNamespace(
        customer_id=customer_id,
        consent_status=ConsentStatus.GRANTED,
    )

    assert latest_consent_by_customer([latest, older]) == {customer_id: latest}


@pytest.mark.parametrize(
    ("customer", "consent", "expected"),
    [
        (
            Customer(
                display_name="Linked",
                status=CustomerStatus.ACTIVE,
                archived_at=None,
                telegram_chat_id=123,
            ),
            NotificationConsent(
                customer_id=uuid.uuid4(),
                consent_type=ConsentType.TELEGRAM_REMINDERS,
                consent_status=ConsentStatus.GRANTED,
                source="test",
            ),
            True,
        ),
        (
            Customer(
                display_name="Opted out",
                status=CustomerStatus.ACTIVE,
                archived_at=None,
                telegram_chat_id=123,
            ),
            NotificationConsent(
                customer_id=uuid.uuid4(),
                consent_type=ConsentType.TELEGRAM_REMINDERS,
                consent_status=ConsentStatus.REVOKED,
                source="test",
            ),
            False,
        ),
        (
            Customer(
                display_name="Not linked",
                status=CustomerStatus.ACTIVE,
                archived_at=None,
                telegram_chat_id=None,
            ),
            NotificationConsent(
                customer_id=uuid.uuid4(),
                consent_type=ConsentType.TELEGRAM_REMINDERS,
                consent_status=ConsentStatus.GRANTED,
                source="test",
            ),
            False,
        ),
    ],
)
def test_broadcast_only_includes_active_linked_customers_with_current_consent(
    customer: Customer,
    consent: NotificationConsent,
    expected: bool,
) -> None:
    assert broadcast_customer_is_eligible(customer, consent) is expected


def test_finishing_broadcast_clears_content_and_keeps_delivery_summary() -> None:
    completed_at = utc_now()
    broadcast = TelegramBroadcast(
        created_by_telegram_id=456,
        sent_count=0,
        failed_count=0,
        skipped_count=0,
        ambiguous_count=0,
        status=TelegramBroadcastStatus.SENDING,
        content_text="campaign text",
        media_type="VIDEO",
        media_file_id="telegram-video-file-id",
        lease_until=utc_now(),
        completed_at=None,
    )

    finish_broadcast(
        broadcast,
        {
            TelegramBroadcastDeliveryStatus.SENT: 3,
            TelegramBroadcastDeliveryStatus.FAILED: 1,
        },
        completed_at,
    )

    assert broadcast.status == TelegramBroadcastStatus.COMPLETED
    assert (broadcast.sent_count, broadcast.failed_count) == (3, 1)
    assert broadcast.content_text is None
    assert broadcast.media_type is None
    assert broadcast.media_file_id is None
    assert broadcast.lease_until is None
    assert broadcast.completed_at == completed_at


def test_confirm_creates_outbox_once_and_is_idempotent() -> None:
    broadcast = TelegramBroadcast(
        id=uuid.uuid4(),
        created_by_telegram_id=456,
        status=TelegramBroadcastStatus.DRAFT,
        recipient_count=3,
    )
    db = Mock(spec=Session)
    db.get.return_value = broadcast

    service = TelegramBroadcastService(db)
    assert service.confirm(broadcast.id, 456) == (True, 3)
    assert broadcast.status == TelegramBroadcastStatus.QUEUED
    assert db.add.call_count == 1
    event = db.add.call_args.args[0]
    assert isinstance(event, OutboxEvent)
    assert event.aggregate_type == "telegram_broadcast"
    assert event.aggregate_id == broadcast.id
    assert event.status == OutboxStatus.PENDING

    assert service.confirm(broadcast.id, 456) == (False, 3)
    assert db.add.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("media_type", "file_id", "method"),
    [
        ("PHOTO", "photo-id", "send_photo"),
        ("VIDEO", "video-id", "send_video"),
        (None, None, "send_message"),
    ],
)
async def test_broadcast_sends_telegram_file_ids_without_downloading_media(
    media_type: str | None,
    file_id: str | None,
    method: str,
) -> None:
    class FakeBot:
        def __init__(self) -> None:
            self.call: tuple[str, dict[str, object]] | None = None

        async def send_photo(self, **kwargs: object) -> None:
            self.call = ("send_photo", kwargs)

        async def send_video(self, **kwargs: object) -> None:
            self.call = ("send_video", kwargs)

        async def send_message(self, **kwargs: object) -> None:
            self.call = ("send_message", kwargs)

    bot = FakeBot()
    status, error_code = await _send_to_recipient(
        bot, 456, "teks", media_type, file_id
    )

    assert status == TelegramBroadcastDeliveryStatus.SENT
    assert error_code is None
    assert bot.call is not None
    assert bot.call[0] == method
    if media_type == "PHOTO":
        assert bot.call[1]["photo"] == file_id
    elif media_type == "VIDEO":
        assert bot.call[1]["video"] == file_id
