"""Build and send customer expiration reminders through Telegram."""

import uuid
from html import escape

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import BusinessRuleError
from app.db.session import SessionLocal
from app.modules.customers.models import Customer, NotificationConsent
from app.modules.notifications.models import Notification
from app.modules.products.models import Product, ProductVariant
from app.modules.renewals.models import RenewalOffer
from app.modules.rentals.models import Rental
from app.shared.datetime_utils import current_wib_date, utc_now
from app.shared.enums import (
    ConsentStatus,
    ConsentType,
    RenewalOfferStatus,
    RentalStatus,
)
from app.shared.money import format_idr

INDONESIAN_MONTHS = (
    "Januari",
    "Februari",
    "Maret",
    "April",
    "Mei",
    "Juni",
    "Juli",
    "Agustus",
    "September",
    "Oktober",
    "November",
    "Desember",
)
DURATION_LABELS = {
    "DAYS": "hari",
    "WEEKS": "minggu",
    "MONTHS": "bulan",
    "YEARS": "tahun",
}


def _has_granted_consent(
    db: Session,
    customer_id: uuid.UUID,
    consent_type: ConsentType,
) -> bool:
    consent = db.scalar(
        select(NotificationConsent)
        .where(
            NotificationConsent.customer_id == customer_id,
            NotificationConsent.consent_type == consent_type,
        )
        .order_by(
            func.coalesce(
                NotificationConsent.revoked_at,
                NotificationConsent.consented_at,
                NotificationConsent.created_at,
            ).desc(),
            NotificationConsent.created_at.desc(),
        )
        .limit(1)
    )
    return consent is not None and consent.consent_status == ConsentStatus.GRANTED


def build_reminder_message(
    db: Session,
    notification_id: uuid.UUID,
) -> tuple[int, str, InlineKeyboardMarkup | None]:
    notification = db.get(Notification, notification_id)
    if notification is None:
        raise BusinessRuleError("Notification no longer exists.")

    rental = db.get(Rental, notification.rental_id)
    customer = db.get(Customer, notification.customer_id)
    if (
        rental is None
        or customer is None
        or rental.archived_at is not None
        or customer.archived_at is not None
        or customer.status != "ACTIVE"
        or customer.telegram_chat_id is None
        or rental.status not in (RentalStatus.ACTIVE, RentalStatus.SCHEDULED)
        or rental.expiration_version != notification.expiration_version
        or rental.expiration_date < current_wib_date()
        or not _has_granted_consent(
            db,
            customer.id,
            ConsentType.TELEGRAM_REMINDERS,
        )
    ):
        raise BusinessRuleError("Rental or Telegram reminder eligibility changed before delivery.")

    product = db.get(Product, rental.product_id)
    variant = db.get(ProductVariant, rental.product_variant_id)
    if product is None or variant is None:
        raise BusinessRuleError("Rental product or variant no longer exists.")

    today = current_wib_date()
    days_remaining = (rental.expiration_date - today).days
    remaining_label = "hari ini" if days_remaining == 0 else f"{days_remaining} hari lagi"
    expiration_label = (
        f"{rental.expiration_date.day} "
        f"{INDONESIAN_MONTHS[rental.expiration_date.month - 1]} "
        f"{rental.expiration_date.year}"
    )
    text = (
        f"Halo {escape(customer.display_name)},\n\n"
        f"Pengingat masa sewa produk digital Anda:\n"
        f"Produk: <b>{escape(product.name)}</b>\n"
        f"Varian: <b>{escape(variant.name)}</b>\n"
        f"Berakhir: <b>{expiration_label}</b>\n"
        f"Sisa waktu: <b>{remaining_label}</b>\n"
    )

    keyboard: InlineKeyboardMarkup | None = None
    if _has_granted_consent(
        db,
        customer.id,
        ConsentType.TELEGRAM_RENEWAL_OFFERS,
    ):
        offers = list(
            db.scalars(
                select(RenewalOffer)
                .where(
                    RenewalOffer.rental_id == rental.id,
                    RenewalOffer.customer_id == customer.id,
                    RenewalOffer.status == RenewalOfferStatus.ACTIVE,
                    RenewalOffer.expires_at > utc_now(),
                )
                .order_by(RenewalOffer.created_at)
            ).all()
        )
        if offers:
            text += "\nPilih opsi perpanjangan yang ditawarkan:"
            rows = [
                [
                    InlineKeyboardButton(
                        text=(
                            f"{offer.offered_duration_value} "
                            f"{DURATION_LABELS[str(offer.offered_duration_unit)]} · "
                            f"{format_idr(offer.offered_price)}"
                        ),
                        callback_data=f"offer_sel:{offer.id}",
                    ),
                    InlineKeyboardButton(
                        text="Tolak",
                        callback_data=f"offer_dec:{offer.id}",
                    ),
                ]
                for offer in offers
            ]
            keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

    return customer.telegram_chat_id, text, keyboard


async def send_telegram_reminder(notification_id: uuid.UUID) -> int:
    with SessionLocal() as db:
        chat_id, text, keyboard = build_reminder_message(db, notification_id)

    async with Bot(token=settings.TELEGRAM_BOT_TOKEN) as bot:
        sent_message = await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    return sent_message.message_id
