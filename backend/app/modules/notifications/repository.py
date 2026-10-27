"""Database repository for notifications and outbox events."""

import uuid
from datetime import date, datetime

from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from app.modules.customers.models import Customer
from app.modules.notifications.models import Notification, OutboxEvent
from app.modules.products.models import Product, ProductVariant
from app.modules.rentals.models import Rental
from app.shared.pagination import PaginationParams


class NotificationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_notifications(self, params: PaginationParams) -> tuple[list[tuple], int]:
        base_stmt = select(Notification)
        total = self.db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0
        stmt = (
            select(
                Notification,
                Customer.display_name,
                Customer.telegram_username,
                Product.name,
                ProductVariant.name,
                Rental.expiration_date,
            )
            .outerjoin(Customer, Customer.id == Notification.customer_id)
            .outerjoin(Rental, Rental.id == Notification.rental_id)
            .outerjoin(Product, Product.id == Rental.product_id)
            .outerjoin(ProductVariant, ProductVariant.id == Rental.product_variant_id)
            .order_by(Notification.scheduled_at.desc())
            .offset(params.offset)
            .limit(params.page_size)
        )
        items = list(self.db.execute(stmt).all())
        return items, int(total)

    def get_by_rental_version_stage(
        self,
        rental_id: uuid.UUID,
        expiration_version: int,
        reminder_stage: str,
    ) -> Notification | None:
        stmt = select(Notification).where(
            Notification.rental_id == rental_id,
            Notification.expiration_version == expiration_version,
            Notification.reminder_stage == reminder_stage,
        )
        return self.db.scalar(stmt)

    def get_for_rental_versions(
        self,
        rental_versions: set[tuple[uuid.UUID, int]],
    ) -> list[Notification]:
        if not rental_versions:
            return []
        stmt = select(Notification).where(
            tuple_(Notification.rental_id, Notification.expiration_version).in_(
                list(rental_versions)
            )
        )
        return list(self.db.scalars(stmt).all())

    def create_notification(self, notification: Notification) -> Notification:
        self.db.add(notification)
        self.db.flush()
        return notification

    def get_notification(
        self,
        notification_id: uuid.UUID,
        for_update: bool = False,
    ) -> Notification | None:
        stmt = select(Notification).where(Notification.id == notification_id)
        if for_update:
            stmt = stmt.with_for_update()
        return self.db.scalar(stmt)

    def get_due_rentals(self, expiration_dates: set[date]) -> list[Rental]:
        stmt = (
            select(Rental)
            .where(
                Rental.expiration_date.in_(expiration_dates),
                Rental.archived_at.is_(None),
                Rental.status.in_(("ACTIVE", "SCHEDULED")),
            )
            .with_for_update(skip_locked=True)
        )
        return list(self.db.scalars(stmt).all())

    def get_due_notifications(self, now: datetime) -> list[Notification]:
        stmt = (
            select(Notification)
            .where(
                Notification.status == "SCHEDULED",
                Notification.scheduled_at <= now,
            )
            .order_by(Notification.scheduled_at)
            .with_for_update(skip_locked=True)
        )
        return list(self.db.scalars(stmt).all())

    def get_due_outbox_events(self, now: datetime, limit: int = 100) -> list[OutboxEvent]:
        stmt = (
            select(OutboxEvent)
            .where(
                OutboxEvent.status.in_(("PENDING", "PROCESSING")),
                OutboxEvent.available_at <= now,
            )
            .order_by(OutboxEvent.available_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(self.db.scalars(stmt).all())

    def has_pending_outbox_event(self, notification_id: uuid.UUID) -> bool:
        stmt = select(OutboxEvent.id).where(
            OutboxEvent.aggregate_type == "notification",
            OutboxEvent.aggregate_id == notification_id,
            OutboxEvent.status.in_(("PENDING", "PROCESSING")),
        )
        return self.db.scalar(stmt) is not None

    def get_pending_outbox_notification_ids(
        self,
        notification_ids: set[uuid.UUID],
    ) -> set[uuid.UUID]:
        if not notification_ids:
            return set()
        stmt = (
            select(OutboxEvent.aggregate_id)
            .where(
                OutboxEvent.aggregate_type == "notification",
                OutboxEvent.aggregate_id.in_(notification_ids),
                OutboxEvent.status.in_(("PENDING", "PROCESSING")),
            )
            .distinct()
        )
        return set(self.db.scalars(stmt).all())
