"""Inline keyboards for Telegram renewal offers and customer actions."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.modules.renewals.schemas import RenewalOfferRead
from app.modules.telegram.callbacks import OfferDeclineCallback, OfferSelectionCallback
from app.shared.money import format_idr


def build_renewal_offer_keyboard(offers: list[RenewalOfferRead]) -> InlineKeyboardMarkup:
    """Build inline keyboard buttons from snapshot renewal offers plus a decline option."""
    rows: list[list[InlineKeyboardButton]] = []
    for offer in offers:
        price_label = format_idr(offer.offered_price)
        unit_label = offer.offered_duration_unit.value.title()
        btn_text = f"Perpanjang {offer.offered_duration_value} {unit_label} — {price_label}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=btn_text,
                    callback_data=OfferSelectionCallback(offer_id=str(offer.id)).pack(),
                )
            ]
        )

    if offers:
        first = offers[0]
        rows.append(
            [
                InlineKeyboardButton(
                    text="Tidak Perpanjang Sekarang",
                    callback_data=OfferDeclineCallback(
                        rental_id=str(first.rental_id),
                        offer_id=str(first.id),
                    ).pack(),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)
