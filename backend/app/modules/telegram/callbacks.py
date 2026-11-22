"""CallbackData definitions for Telegram inline keyboards (aiogram 3.x)."""

from aiogram.filters.callback_data import CallbackData


class OfferSelectionCallback(CallbackData, prefix="offer_sel"):
    offer_id: str


class OfferDeclineCallback(CallbackData, prefix="offer_dec"):
    offer_id: str


class RenewalRentalCallback(CallbackData, prefix="renew_rental"):
    rental_id: str


class RenewalMonthCallback(CallbackData, prefix="renew_month"):
    rental_id: str
    months: int
