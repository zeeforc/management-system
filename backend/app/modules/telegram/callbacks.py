"""CallbackData definitions for Telegram inline keyboards (aiogram 3.x)."""

from aiogram.filters.callback_data import CallbackData


class OfferSelectionCallback(CallbackData, prefix="offer_sel"):
    offer_id: str


class OfferDeclineCallback(CallbackData, prefix="offer_dec"):
    offer_id: str
