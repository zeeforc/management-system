"""Business service for customer management, Telegram linking tokens, and consent history."""

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import BusinessRuleError, NotFoundError
from app.core.security import generate_secure_token
from app.modules.audit.models import AuditLog
from app.modules.customers.models import Customer, NotificationConsent, TelegramLinkToken
from app.modules.customers.repository import CustomerRepository
from app.modules.customers.schemas import (
    ConsentRead,
    ConsentRecordRequest,
    CustomerCreate,
    CustomerRead,
    CustomerUpdate,
    TelegramLinkTokenResponse,
)
from app.shared.datetime_utils import utc_now
from app.shared.enums import ActorType, ConsentStatus, ConsentType
from app.shared.pagination import PaginatedResponse, PaginationParams


def ensure_initial_telegram_consents(db: Session, customer_id: uuid.UUID) -> bool:
    recorded_types = set(
        db.scalars(
            select(NotificationConsent.consent_type).where(
                NotificationConsent.customer_id == customer_id,
            )
        ).all()
    )
    now = utc_now()
    added = False
    for consent_type in (
        ConsentType.TELEGRAM_REMINDERS,
        ConsentType.TELEGRAM_RENEWAL_OFFERS,
    ):
        if consent_type not in recorded_types:
            db.add(
                NotificationConsent(
                    customer_id=customer_id,
                    consent_type=consent_type,
                    consent_status=ConsentStatus.GRANTED,
                    source="ADMIN_CONFIRMED",
                    consented_at=now,
                )
            )
            added = True
    return added


class CustomerService:
    def __init__(self, db: Session, actor_id: str | None = None) -> None:
        self.db = db
        self.repo = CustomerRepository(db)
        self.actor_id = actor_id

    def _audit(self, action: str, entity_id: str, before: dict | None, after: dict | None) -> None:
        log = AuditLog(
            actor_type=ActorType.ADMIN,
            actor_id=self.actor_id,
            action=action,
            entity_type="Customer",
            entity_id=entity_id,
            before_data=before,
            after_data=after,
        )
        self.db.add(log)

    def list_customers(self, params: PaginationParams) -> PaginatedResponse[CustomerRead]:
        items, total = self.repo.list_customers(params)
        return PaginatedResponse.create(
            items=[CustomerRead.model_validate(item) for item in items],
            total=total,
            params=params,
        )

    def get_customer(self, customer_id: uuid.UUID) -> CustomerRead:
        customer = self.repo.get_customer(customer_id)
        if customer is None:
            raise NotFoundError("Customer", customer_id)
        return CustomerRead.model_validate(customer)

    def create_customer(self, payload: CustomerCreate) -> CustomerRead:
        username = (
            payload.telegram_username.lstrip("@").strip() or None
            if payload.telegram_username
            else None
        )
        customer = Customer(
            display_name=payload.display_name.strip(),
            telegram_username=username,
            status=payload.status,
            internal_notes=payload.internal_notes,
        )
        self.repo.create_customer(customer)
        telegram_consents_granted = (
            ensure_initial_telegram_consents(self.db, customer.id)
            if username
            else False
        )
        self._audit(
            "customer.created",
            str(customer.id),
            None,
            {
                "display_name": customer.display_name,
                "telegram_consents_granted": telegram_consents_granted,
            },
        )
        self.db.commit()
        self.db.refresh(customer)
        return CustomerRead.model_validate(customer)

    def update_customer(self, customer_id: uuid.UUID, payload: CustomerUpdate) -> CustomerRead:
        customer = self.repo.get_customer(customer_id)
        if customer is None:
            raise NotFoundError("Customer", customer_id)
        before = {"display_name": customer.display_name, "status": customer.status}
        telegram_consents_granted = False
        if payload.display_name is not None:
            customer.display_name = payload.display_name.strip()
        if "telegram_username" in payload.model_fields_set:
            username = payload.telegram_username
            customer.telegram_username = (
                username.lstrip("@").strip() or None if username is not None else None
            )
            if customer.telegram_username:
                telegram_consents_granted = ensure_initial_telegram_consents(self.db, customer.id)
        if payload.status is not None:
            customer.status = payload.status
        if "internal_notes" in payload.model_fields_set:
            customer.internal_notes = payload.internal_notes
        self._audit(
            "customer.updated",
            str(customer.id),
            before,
            {
                "display_name": customer.display_name,
                "status": customer.status,
                "telegram_consents_granted": telegram_consents_granted,
            },
        )
        self.db.commit()
        self.db.refresh(customer)
        return CustomerRead.model_validate(customer)

    def archive_customer(self, customer_id: uuid.UUID) -> CustomerRead:
        customer = self.repo.get_customer(customer_id)
        if customer is None:
            raise NotFoundError("Customer", customer_id)
        if customer.archived_at is not None:
            raise BusinessRuleError("Customer is already archived.")
        customer.archived_at = utc_now()
        self._audit(
            "customer.archived", str(customer.id), None, {"archived_at": str(customer.archived_at)}
        )
        self.db.commit()
        self.db.refresh(customer)
        return CustomerRead.model_validate(customer)

    def generate_telegram_link_token(self, customer_id: uuid.UUID) -> TelegramLinkTokenResponse:
        customer = self.repo.get_customer(customer_id)
        if customer is None:
            raise NotFoundError("Customer", customer_id)
        raw_token, token_hash = generate_secure_token(24)
        expires_at = utc_now() + timedelta(minutes=settings.TELEGRAM_LINK_TOKEN_EXPIRE_MINUTES)
        link_token = TelegramLinkToken(
            customer_id=customer.id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.repo.create_link_token(link_token)
        self.db.commit()
        return TelegramLinkTokenResponse(
            customer_id=customer.id,
            raw_token=raw_token,
            expires_at=expires_at,
            deep_link_command=f"/start link_{raw_token}",
        )

    def record_consent(self, customer_id: uuid.UUID, payload: ConsentRecordRequest) -> ConsentRead:
        customer = self.repo.get_customer(customer_id)
        if customer is None:
            raise NotFoundError("Customer", customer_id)
        now = utc_now()
        consent = NotificationConsent(
            customer_id=customer.id,
            consent_type=payload.consent_type,
            consent_status=payload.consent_status,
            source=payload.source,
            consented_at=now if payload.consent_status == ConsentStatus.GRANTED else None,
            revoked_at=now if payload.consent_status == ConsentStatus.REVOKED else None,
        )
        self.repo.create_consent(consent)
        self._audit(
            "customer.consent_recorded",
            str(customer.id),
            None,
            {"consent_type": payload.consent_type, "consent_status": payload.consent_status},
        )
        self.db.commit()
        self.db.refresh(consent)
        return ConsentRead.model_validate(consent)
