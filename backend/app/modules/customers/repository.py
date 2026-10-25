"""Database repository for customers, consents, and Telegram link tokens."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.customers.models import Customer, NotificationConsent, TelegramLinkToken
from app.shared.pagination import PaginationParams


class CustomerRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_customers(self, params: PaginationParams) -> tuple[list[Customer], int]:
        base_stmt = select(Customer).where(Customer.archived_at.is_(None))
        total = self.db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0
        items = list(
            self.db.scalars(
                base_stmt.order_by(Customer.created_at.desc())
                .offset(params.offset)
                .limit(params.page_size)
            ).all()
        )
        return items, int(total)

    def get_customer(self, customer_id: uuid.UUID) -> Customer | None:
        return self.db.scalar(select(Customer).where(Customer.id == customer_id))

    def get_by_telegram_user_id(self, telegram_user_id: int) -> Customer | None:
        return self.db.scalar(
            select(Customer).where(Customer.telegram_user_id == telegram_user_id)
        )

    def create_customer(self, customer: Customer) -> Customer:
        self.db.add(customer)
        self.db.flush()
        return customer

    def create_link_token(self, link_token: TelegramLinkToken) -> TelegramLinkToken:
        self.db.add(link_token)
        self.db.flush()
        return link_token

    def create_consent(self, consent: NotificationConsent) -> NotificationConsent:
        self.db.add(consent)
        self.db.flush()
        return consent
