"""Integration coverage for durable reminder scheduling and customer bot workflows."""

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from aiogram.methods import SendMessage
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import BusinessRuleError
from app.core.security import generate_secure_token
from app.modules.customers.models import (
    NotificationConsent,
    TelegramLinkToken,
)
from app.modules.notifications.models import (
    Notification,
    NotificationAttempt,
    NotificationResponse,
    OutboxEvent,
)
from app.modules.notifications.service import NotificationService
from app.modules.payments.models import Payment
from app.modules.renewals.models import RenewalOffer, RentalRenewal
from app.modules.renewals.schemas import RenewalApprovalRequest, RenewalRequestCreate
from app.modules.renewals.service import RenewalService
from app.modules.telegram.service import TelegramService
from app.shared.datetime_utils import current_wib_date, utc_now
from app.shared.enums import (
    AttemptResultStatus,
    ConsentStatus,
    ConsentType,
    NotificationStatus,
    OutboxStatus,
    PaymentStatus,
    ReminderStage,
    RenewalModel,
    RenewalOfferStatus,
    RenewalStatus,
)

WIB = ZoneInfo("Asia/Jakarta")


def _grant_consent(db: Session, customer_id, consent_type: ConsentType) -> None:
    db.add(
        NotificationConsent(
            customer_id=customer_id,
            consent_type=consent_type,
            consent_status=ConsentStatus.GRANTED,
            source="integration_test",
            consented_at=utc_now(),
        )
    )
    db.flush()


def test_due_reminder_is_persisted_before_outbox_dispatch(
    db: Session,
    customer,
    active_rental,
) -> None:
    customer.telegram_user_id = 987654321
    customer.telegram_chat_id = 987654321
    active_rental.expiration_date = current_wib_date() + timedelta(days=5)
    _grant_consent(db, customer.id, ConsentType.TELEGRAM_REMINDERS)
    db.flush()

    now = datetime.combine(current_wib_date(), time(hour=11), tzinfo=WIB).astimezone(UTC)
    result = NotificationService(db).scan_due_reminders(now)

    notification = db.scalar(
        select(Notification).where(
            Notification.rental_id == active_rental.id,
            Notification.reminder_stage == ReminderStage.H5,
        )
    )
    event = db.scalar(
        select(OutboxEvent).where(
            OutboxEvent.aggregate_id == notification.id,
            OutboxEvent.aggregate_type == "notification",
        )
    )
    assert result["queued"] == 1
    assert notification.status == NotificationStatus.QUEUED
    assert event.status == OutboxStatus.PENDING
    assert notification.attempt_count == 0


def test_due_reminder_without_consent_is_not_queued(
    db: Session,
    customer,
    active_rental,
) -> None:
    customer.telegram_chat_id = 987654321
    active_rental.expiration_date = current_wib_date() + timedelta(days=3)
    db.flush()

    now = datetime.combine(current_wib_date(), time(hour=11), tzinfo=WIB).astimezone(UTC)
    result = NotificationService(db).scan_due_reminders(now)

    notification = db.scalar(
        select(Notification).where(
            Notification.rental_id == active_rental.id,
            Notification.reminder_stage == ReminderStage.H3,
        )
    )
    assert result["rejected"] >= 1
    assert notification.status == NotificationStatus.FAILED_PERMANENT
    assert (
        db.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.aggregate_id == notification.id)
        )
        == 0
    )


def test_offer_selection_is_owned_idempotent_and_does_not_activate_rental(
    db: Session,
    customer,
    active_rental,
) -> None:
    customer.telegram_user_id = 987654321
    customer.telegram_chat_id = 987654321
    _grant_consent(db, customer.id, ConsentType.TELEGRAM_RENEWAL_OFFERS)
    offer = RenewalOffer(
        rental_id=active_rental.id,
        customer_id=customer.id,
        offered_duration_value=1,
        offered_duration_unit="MONTHS",
        offered_price=Decimal("50000.00"),
        currency="IDR",
        renewal_model=RenewalModel.CONTINUOUS,
        status=RenewalOfferStatus.ACTIVE,
        expires_at=utc_now() + timedelta(hours=12),
    )
    db.add(offer)
    db.flush()

    service = TelegramService(db)
    response = service.respond_to_offer(
        offer.id,
        customer.telegram_user_id,
        customer.telegram_chat_id,
    )
    duplicate_response = service.respond_to_offer(
        offer.id,
        customer.telegram_user_id,
        customer.telegram_chat_id,
    )

    renewal = db.scalar(select(RentalRenewal).where(RentalRenewal.rental_id == active_rental.id))
    assert "belum aktif diperpanjang" in response
    assert "sudah tercatat sebelumnya" in duplicate_response
    assert renewal.status == RenewalStatus.PENDING
    assert offer.status == RenewalOfferStatus.SELECTED
    assert (
        db.scalar(
            select(func.count())
            .select_from(NotificationResponse)
            .where(NotificationResponse.renewal_offer_id == offer.id)
        )
        == 1
    )


def test_offer_selection_rejects_another_customer_chat(
    db: Session,
    customer,
    active_rental,
) -> None:
    customer.telegram_user_id = 987654321
    customer.telegram_chat_id = 987654321
    _grant_consent(db, customer.id, ConsentType.TELEGRAM_RENEWAL_OFFERS)
    offer = RenewalOffer(
        rental_id=active_rental.id,
        customer_id=customer.id,
        offered_duration_value=1,
        offered_duration_unit="MONTHS",
        offered_price=Decimal("50000.00"),
        currency="IDR",
        renewal_model=RenewalModel.CONTINUOUS,
        status=RenewalOfferStatus.ACTIVE,
        expires_at=utc_now() + timedelta(hours=12),
    )
    db.add(offer)
    db.flush()

    with pytest.raises(BusinessRuleError):
        TelegramService(db).respond_to_offer(
            offer.id,
            customer.telegram_user_id,
            222333444,
        )

    assert offer.status == RenewalOfferStatus.ACTIVE


def test_expired_rental_offer_requires_admin_confirmed_start_date(
    db: Session,
    customer,
    active_rental,
    admin_user,
) -> None:
    customer.telegram_user_id = 987654321
    customer.telegram_chat_id = 987654321
    active_rental.expiration_date = current_wib_date() - timedelta(days=2)
    _grant_consent(db, customer.id, ConsentType.TELEGRAM_RENEWAL_OFFERS)
    offer = RenewalOffer(
        rental_id=active_rental.id,
        customer_id=customer.id,
        offered_duration_value=1,
        offered_duration_unit="MONTHS",
        offered_price=Decimal("50000.00"),
        currency="IDR",
        renewal_model=RenewalModel.CONTINUOUS,
        status=RenewalOfferStatus.ACTIVE,
        expires_at=utc_now() + timedelta(hours=12),
    )
    db.add(offer)
    db.flush()

    TelegramService(db).respond_to_offer(
        offer.id,
        customer.telegram_user_id,
        customer.telegram_chat_id,
    )
    renewal = db.scalar(select(RentalRenewal).where(RentalRenewal.rental_id == active_rental.id))
    selected_start_date = current_wib_date()
    approved = RenewalService(db).approve_renewal(
        renewal.id,
        RenewalApprovalRequest(
            renewal_model=RenewalModel.IMMEDIATE,
            confirmed_start_date=selected_start_date,
        ),
        admin_user.id,
    )

    assert approved.status == RenewalStatus.APPROVED
    assert approved.new_start_date == selected_start_date
    assert approved.previous_expiration_date < approved.new_start_date


def test_telegram_link_token_is_single_use_and_consent_is_reversible(
    db: Session,
    customer,
) -> None:
    raw_token, token_hash = generate_secure_token(24)
    db.add(
        TelegramLinkToken(
            customer_id=customer.id,
            token_hash=token_hash,
            expires_at=utc_now() + timedelta(minutes=15),
        )
    )
    db.flush()

    service = TelegramService(db)
    linked_name = service.link_customer(raw_token, 987654321, 987654321, "test_user")

    assert linked_name == customer.display_name
    assert customer.telegram_user_id == 987654321
    assert customer.telegram_chat_id == 987654321
    assert customer.telegram_username == "test_user"
    with pytest.raises(BusinessRuleError, match="tidak valid"):
        service.link_customer(raw_token, 987654321, 987654321, "test_user")

    assert service.record_customer_consent(987654321, 987654321, granted=True)
    assert service.record_customer_consent(987654321, 987654321, granted=False)
    assert (
        db.scalar(
            select(func.count())
            .select_from(NotificationConsent)
            .where(NotificationConsent.customer_id == customer.id)
        )
        == 4
    )
    assert not service._has_current_consent(
        customer.id,
        ConsentType.TELEGRAM_REMINDERS,
    )
    assert not service._has_current_consent(
        customer.id,
        ConsentType.TELEGRAM_RENEWAL_OFFERS,
    )


def test_declining_offers_is_idempotent(
    db: Session,
    customer,
    active_rental,
) -> None:
    customer.telegram_user_id = 987654321
    customer.telegram_chat_id = 987654321
    _grant_consent(db, customer.id, ConsentType.TELEGRAM_RENEWAL_OFFERS)
    offer = RenewalOffer(
        rental_id=active_rental.id,
        customer_id=customer.id,
        offered_duration_value=1,
        offered_duration_unit="MONTHS",
        offered_price=Decimal("50000.00"),
        currency="IDR",
        renewal_model=RenewalModel.CONTINUOUS,
        status=RenewalOfferStatus.ACTIVE,
        expires_at=utc_now() + timedelta(hours=12),
    )
    db.add(offer)
    db.flush()

    service = TelegramService(db)
    first_response = service.decline_offer(
        offer.id,
        customer.telegram_user_id,
        customer.telegram_chat_id,
    )
    duplicate_response = service.decline_offer(
        offer.id,
        customer.telegram_user_id,
        customer.telegram_chat_id,
    )

    assert "sudah dicatat" in first_response
    assert "tercatat sebelumnya" in duplicate_response
    assert offer.status == RenewalOfferStatus.DECLINED
    assert (
        db.scalar(
            select(func.count())
            .select_from(NotificationResponse)
            .where(NotificationResponse.renewal_offer_id == offer.id)
        )
        == 1
    )


def test_renewal_completion_requires_verified_payment(
    db: Session,
    customer,
    active_rental,
    admin_user,
) -> None:
    renewal_service = RenewalService(db)
    renewal = renewal_service.create_renewal_request(
        active_rental.id,
        RenewalRequestCreate(
            duration_value=1,
            duration_unit="MONTHS",
            renewal_model=RenewalModel.CONTINUOUS,
            agreed_price=Decimal("50000.00"),
        ),
        created_by=admin_user.id,
    )
    renewal_service.approve_renewal(
        renewal.id,
        RenewalApprovalRequest(renewal_model=RenewalModel.CONTINUOUS),
        admin_user.id,
    )

    with pytest.raises(BusinessRuleError, match="verified payments"):
        renewal_service.complete_renewal(renewal.id, admin_user.id)


def test_renewal_completion_updates_expiration_and_cancels_old_reminders(
    db: Session,
    customer,
    active_rental,
    admin_user,
) -> None:
    notification_service = NotificationService(db)
    old_reminders = notification_service.schedule_rental_reminders(active_rental.id)
    renewal_service = RenewalService(db)
    renewal = renewal_service.create_renewal_request(
        active_rental.id,
        RenewalRequestCreate(
            duration_value=1,
            duration_unit="MONTHS",
            renewal_model=RenewalModel.CONTINUOUS,
            agreed_price=Decimal("50000.00"),
        ),
        created_by=admin_user.id,
    )
    renewal_service.approve_renewal(
        renewal.id,
        RenewalApprovalRequest(renewal_model=RenewalModel.CONTINUOUS),
        admin_user.id,
    )
    db.add(
        Payment(
            customer_id=customer.id,
            rental_id=active_rental.id,
            renewal_id=renewal.id,
            amount=Decimal("50000.00"),
            currency="IDR",
            payment_method="BANK_TRANSFER",
            status=PaymentStatus.PAID,
            verified_at=utc_now(),
            verified_by=admin_user.id,
        )
    )
    db.flush()

    completed = renewal_service.complete_renewal(renewal.id, admin_user.id)

    assert completed.status == RenewalStatus.COMPLETED
    assert active_rental.expiration_version == 2
    assert active_rental.expiration_date == completed.new_expiration_date
    assert all(
        db.get(Notification, reminder.id).status == NotificationStatus.CANCELLED
        for reminder in old_reminders
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.rental_id == active_rental.id,
                Notification.expiration_version == 2,
            )
        )
        == 3
    )


def _queued_notification(db, customer, active_rental) -> Notification:
    customer.telegram_user_id = 987654321
    customer.telegram_chat_id = 987654321
    _grant_consent(db, customer.id, ConsentType.TELEGRAM_REMINDERS)
    notification = Notification(
        rental_id=active_rental.id,
        customer_id=customer.id,
        reminder_stage=ReminderStage.H5,
        expiration_version=active_rental.expiration_version,
        scheduled_at=utc_now(),
        status=NotificationStatus.QUEUED,
        attempt_count=0,
    )
    db.add(notification)
    db.flush()
    db.add(
        OutboxEvent(
            event_type="notification.send",
            aggregate_type="notification",
            aggregate_id=notification.id,
            payload={"notification_id": str(notification.id)},
            status=OutboxStatus.PROCESSING,
            available_at=utc_now() + timedelta(minutes=5),
        )
    )
    db.flush()
    return notification


def _test_session_factory(db: Session):
    return sessionmaker(
        bind=db.get_bind(),
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )


def test_delivery_persists_successful_telegram_attempt(
    db: Session,
    customer,
    active_rental,
    monkeypatch,
) -> None:
    from app.modules.notifications import tasks

    notification = _queued_notification(db, customer, active_rental)
    monkeypatch.setattr(tasks, "SessionLocal", _test_session_factory(db))

    async def successful_send(chat_id, text, reply_markup):
        assert chat_id == customer.telegram_chat_id
        assert "Test Product" in text
        return 456

    monkeypatch.setattr(tasks, "_send_message", successful_send)
    result = tasks.dispatch_reminder_task.run(str(notification.id))
    db.refresh(notification)

    assert result["status"] == "sent"
    assert notification.status == NotificationStatus.SENT
    attempt = db.scalar(
        select(NotificationAttempt).where(NotificationAttempt.notification_id == notification.id)
    )
    assert attempt.result_status == AttemptResultStatus.SUCCESS
    assert attempt.telegram_message_id == 456


def test_delivery_retry_after_is_bounded_and_uses_retry_after(
    db: Session,
    customer,
    active_rental,
    monkeypatch,
) -> None:
    from app.modules.notifications import tasks

    notification = _queued_notification(db, customer, active_rental)
    monkeypatch.setattr(tasks, "SessionLocal", _test_session_factory(db))

    async def rate_limited_send(chat_id, text, reply_markup):
        raise TelegramRetryAfter(
            method=SendMessage(chat_id=chat_id, text=text),
            message="rate limited",
            retry_after=11,
        )

    monkeypatch.setattr(tasks, "_send_message", rate_limited_send)
    result = tasks.dispatch_reminder_task.run(str(notification.id))
    db.refresh(notification)

    retry_event = db.scalar(
        select(OutboxEvent).where(
            OutboxEvent.aggregate_id == notification.id,
            OutboxEvent.event_type == "notification.retry",
        )
    )
    assert result["status"] == "retry_scheduled"
    assert notification.status == NotificationStatus.FAILED_RETRYABLE
    assert retry_event.available_at >= utc_now() + timedelta(seconds=11)


def test_delivery_stops_retrying_after_three_attempts(
    db: Session,
    customer,
    active_rental,
    monkeypatch,
) -> None:
    from app.modules.notifications import tasks

    notification = _queued_notification(db, customer, active_rental)
    notification.attempt_count = 2
    db.flush()
    monkeypatch.setattr(tasks, "SessionLocal", _test_session_factory(db))

    async def rate_limited_send(chat_id, text, reply_markup):
        raise TelegramRetryAfter(
            method=SendMessage(chat_id=chat_id, text=text),
            message="rate limited",
            retry_after=11,
        )

    monkeypatch.setattr(tasks, "_send_message", rate_limited_send)
    result = tasks.dispatch_reminder_task.run(str(notification.id))
    db.refresh(notification)

    assert result["status"] == "failed_permanent"
    assert notification.status == NotificationStatus.FAILED_PERMANENT
    assert notification.attempt_count == 3
    assert (
        db.scalar(
            select(OutboxEvent.id).where(
                OutboxEvent.aggregate_id == notification.id,
                OutboxEvent.event_type == "notification.retry",
            )
        )
        is None
    )


def test_uncertain_telegram_network_result_is_marked_ambiguous(
    db: Session,
    customer,
    active_rental,
    monkeypatch,
) -> None:
    from app.modules.notifications import tasks

    notification = _queued_notification(db, customer, active_rental)
    monkeypatch.setattr(tasks, "SessionLocal", _test_session_factory(db))

    async def uncertain_send(chat_id, text, reply_markup):
        raise TelegramNetworkError(
            method=SendMessage(chat_id=chat_id, text=text),
            message="response lost",
        )

    monkeypatch.setattr(tasks, "_send_message", uncertain_send)
    result = tasks.dispatch_reminder_task.run(str(notification.id))
    db.refresh(notification)

    assert result["status"] == "ambiguous"
    assert notification.status == NotificationStatus.AMBIGUOUS
    assert notification.attempt_count == 1
    assert (
        db.scalar(
            select(OutboxEvent.id).where(
                OutboxEvent.aggregate_id == notification.id,
                OutboxEvent.event_type == "notification.retry",
            )
        )
        is None
    )


def test_outbox_recovers_unstarted_jobs_but_never_retries_ambiguous_sends(
    db: Session,
    customer,
    active_rental,
    monkeypatch,
) -> None:
    from app.workers import scheduled_tasks

    notification = _queued_notification(db, customer, active_rental)
    event = db.scalar(select(OutboxEvent).where(OutboxEvent.aggregate_id == notification.id))
    event.status = OutboxStatus.PENDING
    event.available_at = utc_now()
    db.flush()
    monkeypatch.setattr(scheduled_tasks, "SessionLocal", _test_session_factory(db))

    class DispatcherStub:
        calls = 0

        @classmethod
        def apply_async(cls, args):
            cls.calls += 1

    monkeypatch.setattr(scheduled_tasks, "dispatch_reminder_task", DispatcherStub)
    first_result = scheduled_tasks.process_outbox_events.run()
    db.refresh(event)
    assert first_result["dispatched"] == 1
    assert event.status == OutboxStatus.PROCESSING

    event.available_at = utc_now() - timedelta(seconds=1)
    db.flush()
    recovered_result = scheduled_tasks.process_outbox_events.run()
    assert recovered_result["dispatched"] == 1
    assert DispatcherStub.calls == 2

    notification.status = NotificationStatus.AMBIGUOUS
    event.available_at = utc_now() - timedelta(seconds=1)
    db.flush()
    ambiguous_result = scheduled_tasks.process_outbox_events.run()
    db.refresh(event)

    assert ambiguous_result["dispatched"] == 0
    assert event.status == OutboxStatus.PROCESSED
    assert DispatcherStub.calls == 2
