"""Business service for renewal offers and transactional renewal completion (Section 8.1)."""

import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.modules.audit.models import AuditLog
from app.modules.notifications.models import Notification, OutboxEvent
from app.modules.payments.models import Payment
from app.modules.renewals.models import RenewalOffer, RentalRenewal
from app.modules.renewals.repository import RenewalRepository
from app.modules.renewals.schemas import (
    RenewalApprovalRequest,
    RenewalOfferCreate,
    RenewalOfferRead,
    RenewalRead,
    RenewalRequestCreate,
)
from app.modules.rentals.repository import RentalRepository
from app.shared.datetime_utils import (
    calculate_reminder_dates,
    calculate_reminder_scheduled_utc,
    calculate_renewal_dates,
    current_wib_date,
    utc_now,
)
from app.shared.enums import (
    ActorType,
    NotificationStatus,
    OutboxStatus,
    ReminderStage,
    RenewalOfferStatus,
    RenewalStatus,
    RentalStatus,
)
from app.shared.money import normalize_money, validate_currency
from app.shared.pagination import PaginatedResponse, PaginationParams


class RenewalService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = RenewalRepository(db)
        self.rental_repo = RentalRepository(db)

    def _audit(
        self,
        action: str,
        renewal: RentalRenewal,
        admin_id: uuid.UUID,
        before_status: RenewalStatus,
    ) -> None:
        self.db.add(
            AuditLog(
                actor_type=ActorType.ADMIN,
                actor_id=str(admin_id),
                action=action,
                entity_type="RentalRenewal",
                entity_id=str(renewal.id),
                before_data={"status": before_status},
                after_data={"status": renewal.status},
            )
        )

    def list_renewals(self, params: PaginationParams) -> PaginatedResponse[RenewalRead]:
        items, total = self.repo.list_renewals(params)
        return PaginatedResponse.create(
            items=[RenewalRead.model_validate(item) for item in items],
            total=total,
            params=params,
        )

    def create_offer(self, payload: RenewalOfferCreate) -> RenewalOfferRead:
        rental = self.rental_repo.get_rental(payload.rental_id)
        if rental is None:
            raise NotFoundError("Rental", payload.rental_id)

        currency = validate_currency(payload.currency)
        price = normalize_money(payload.offered_price, currency)
        offer = RenewalOffer(
            rental_id=rental.id,
            customer_id=rental.customer_id,
            offered_duration_value=payload.offered_duration_value,
            offered_duration_unit=payload.offered_duration_unit,
            offered_price=price,
            currency=currency,
            renewal_model=payload.renewal_model,
            status=RenewalOfferStatus.ACTIVE,
            expires_at=utc_now() + timedelta(hours=payload.expires_in_hours),
        )
        self.repo.create_offer(offer)
        self.db.commit()
        self.db.refresh(offer)
        return RenewalOfferRead.model_validate(offer)

    def create_renewal_request(
        self,
        rental_id: uuid.UUID,
        payload: RenewalRequestCreate,
        created_by: uuid.UUID | None = None,
    ) -> RenewalRead:
        rental = self.rental_repo.get_rental(rental_id, for_update=True)
        if rental is None:
            raise NotFoundError("Rental", rental_id)

        try:
            new_start_date, new_expiration_date = calculate_renewal_dates(
                previous_expiration_date=rental.expiration_date,
                duration_value=payload.duration_value,
                duration_unit=payload.duration_unit,
                renewal_model=payload.renewal_model,
                confirmed_start_date=payload.confirmed_start_date,
            )
        except ValueError as exc:
            raise BusinessRuleError(str(exc)) from exc

        currency = validate_currency(payload.currency)
        agreed_price = normalize_money(payload.agreed_price, currency)

        renewal = RentalRenewal(
            rental_id=rental.id,
            previous_start_date=rental.start_date,
            previous_expiration_date=rental.expiration_date,
            new_start_date=new_start_date,
            new_expiration_date=new_expiration_date,
            duration_value=payload.duration_value,
            duration_unit=payload.duration_unit,
            renewal_model=payload.renewal_model,
            agreed_price=agreed_price,
            currency=currency,
            status=RenewalStatus.PENDING,
            created_by=created_by,
        )
        self.repo.create_renewal(renewal)
        self.db.commit()
        self.db.refresh(renewal)
        return RenewalRead.model_validate(renewal)

    def approve_renewal(
        self,
        renewal_id: uuid.UUID,
        payload: RenewalApprovalRequest,
        admin_id: uuid.UUID,
    ) -> RenewalRead:
        renewal = self.repo.get_renewal(renewal_id, for_update=True)
        if renewal is None:
            raise NotFoundError("Renewal", renewal_id)
        if renewal.status != RenewalStatus.PENDING:
            raise ConflictError("Only pending renewal requests can be approved.")

        rental = self.rental_repo.get_rental(renewal.rental_id, for_update=True)
        if rental is None:
            raise NotFoundError("Rental", renewal.rental_id)
        try:
            new_start_date, new_expiration_date = calculate_renewal_dates(
                previous_expiration_date=rental.expiration_date,
                duration_value=renewal.duration_value,
                duration_unit=renewal.duration_unit,
                renewal_model=payload.renewal_model,
                confirmed_start_date=payload.confirmed_start_date,
            )
        except ValueError as exc:
            raise BusinessRuleError(str(exc)) from exc

        old_status = renewal.status
        renewal.new_start_date = new_start_date
        renewal.new_expiration_date = new_expiration_date
        renewal.renewal_model = payload.renewal_model
        renewal.status = RenewalStatus.APPROVED
        self._audit("renewal.approved", renewal, admin_id, old_status)
        self.db.commit()
        self.db.refresh(renewal)
        return RenewalRead.model_validate(renewal)

    def reject_renewal(self, renewal_id: uuid.UUID, admin_id: uuid.UUID) -> RenewalRead:
        renewal = self.repo.get_renewal(renewal_id, for_update=True)
        if renewal is None:
            raise NotFoundError("Renewal", renewal_id)
        if renewal.status not in (RenewalStatus.PENDING, RenewalStatus.APPROVED):
            raise ConflictError("This renewal request can no longer be rejected.")

        old_status = renewal.status
        renewal.status = RenewalStatus.REJECTED
        self._audit("renewal.rejected", renewal, admin_id, old_status)
        self.db.commit()
        self.db.refresh(renewal)
        return RenewalRead.model_validate(renewal)

    def complete_renewal(self, renewal_id: uuid.UUID, admin_id: uuid.UUID) -> RenewalRead:
        renewal = self.repo.get_renewal(renewal_id, for_update=True)
        if renewal is None:
            raise NotFoundError("Renewal", renewal_id)
        if renewal.status != RenewalStatus.APPROVED:
            raise ConflictError("Only an approved renewal can be completed.")

        rental = self.rental_repo.get_rental(renewal.rental_id, for_update=True)
        if rental is None:
            raise NotFoundError("Rental", renewal.rental_id)
        verified_amount = self.db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.renewal_id == renewal.id,
                Payment.rental_id == rental.id,
                Payment.customer_id == rental.customer_id,
                Payment.currency == renewal.currency,
                Payment.status == "PAID",
                Payment.verified_at.is_not(None),
            )
        )
        if renewal.agreed_price > 0 and verified_amount < renewal.agreed_price:
            raise BusinessRuleError(
                "Renewal cannot be completed until its verified payments cover the agreed price."
            )

        old_version = rental.expiration_version
        for notification in self.db.scalars(
            select(Notification)
            .where(
                Notification.rental_id == rental.id,
                Notification.expiration_version == old_version,
                Notification.status.in_(
                    (
                        NotificationStatus.SCHEDULED,
                        NotificationStatus.QUEUED,
                        NotificationStatus.FAILED_RETRYABLE,
                    )
                ),
            )
            .with_for_update()
        ).all():
            notification.status = NotificationStatus.CANCELLED
            notification.last_error = "Rental expiration changed after renewal completion."
            for event in self.db.scalars(
                select(OutboxEvent)
                .where(
                    OutboxEvent.aggregate_type == "notification",
                    OutboxEvent.aggregate_id == notification.id,
                    OutboxEvent.status.in_((OutboxStatus.PENDING, OutboxStatus.PROCESSING)),
                )
                .with_for_update()
            ).all():
                event.status = OutboxStatus.FAILED
                event.processed_at = utc_now()
                event.last_error = "Rental expiration changed."

        rental.start_date = renewal.new_start_date
        rental.expiration_date = renewal.new_expiration_date
        rental.duration_value = renewal.duration_value
        rental.duration_unit = renewal.duration_unit
        rental.agreed_price = renewal.agreed_price
        rental.currency = renewal.currency
        rental.renewal_model = renewal.renewal_model
        rental.expiration_version += 1
        rental.status = (
            RentalStatus.SCHEDULED
            if renewal.new_start_date > current_wib_date()
            else RentalStatus.ACTIVE
        )

        today = current_wib_date()
        reminder_dates = calculate_reminder_dates(renewal.new_expiration_date)
        for stage in (ReminderStage.H5, ReminderStage.H3, ReminderStage.H1):
            self.db.add(
                Notification(
                    rental_id=rental.id,
                    customer_id=rental.customer_id,
                    reminder_stage=stage,
                    expiration_version=rental.expiration_version,
                    scheduled_at=calculate_reminder_scheduled_utc(
                        renewal.new_expiration_date,
                        stage,
                        settings.DEFAULT_REMINDER_SEND_HOUR_WIB,
                        settings.DEFAULT_REMINDER_SEND_MINUTE_WIB,
                    ),
                    status=(
                        NotificationStatus.CANCELLED
                        if reminder_dates[stage] < today
                        else NotificationStatus.SCHEDULED
                    ),
                    attempt_count=0,
                )
            )

        old_status = renewal.status
        renewal.status = RenewalStatus.COMPLETED
        renewal.completed_at = utc_now()
        self._audit("renewal.completed", renewal, admin_id, old_status)
        for offer in self.db.scalars(
            select(RenewalOffer).where(
                RenewalOffer.rental_id == rental.id,
                RenewalOffer.status == RenewalOfferStatus.ACTIVE,
            )
        ).all():
            offer.status = RenewalOfferStatus.INVALIDATED
        self.db.commit()
        self.db.refresh(renewal)
        return RenewalRead.model_validate(renewal)
