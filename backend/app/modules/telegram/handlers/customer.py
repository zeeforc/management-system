"""Customer Telegram linking, consent, and renewal-offer callbacks."""

import uuid

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from app.core.exceptions import BusinessRuleError
from app.db.session import SessionLocal
from app.modules.telegram.callbacks import OfferDeclineCallback, OfferSelectionCallback
from app.modules.telegram.service import TelegramService

customer_router = Router(name="telegram_customer")


@customer_router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    sender = message.from_user
    if sender is None or message.chat.type != "private":
        await message.answer("Tautkan akun melalui chat pribadi dengan bot ini.")
        return

    parts = (message.text or "").strip().split(maxsplit=1)
    if len(parts) == 2 and parts[1].startswith("link_"):
        token = parts[1][5:]
        if not token:
            await message.answer("Tautan tidak valid. Minta admin membuat tautan baru.")
            return
        try:
            with SessionLocal() as db:
                customer_name = TelegramService(db).link_customer(
                    token,
                    sender.id,
                    message.chat.id,
                    sender.username,
                )
        except BusinessRuleError as exc:
            await message.answer(f"⚠️ {exc}")
            return

        await message.answer(
            f"Halo {customer_name}, akun Telegram Anda berhasil ditautkan.\n\n"
            "Untuk mengaktifkan pengingat dan penawaran perpanjangan, kirim /consent. "
            "Kirim /stop kapan saja untuk mencabut persetujuan."
        )
        return

    await message.answer(
        "👋 Selamat datang di Bot Rental Monitoring.\n"
        "Minta tautan akun dari admin, lalu buka tautan tersebut melalui chat pribadi "
        "dengan bot ini. Gunakan /help untuk melihat perintah pelanggan."
    )


@customer_router.message(Command("consent"))
async def cmd_consent(message: Message) -> None:
    if message.from_user is None or message.chat.type != "private":
        await message.answer("Perintah ini hanya tersedia melalui chat pribadi.")
        return
    with SessionLocal() as db:
        linked = TelegramService(db).record_customer_consent(
            message.from_user.id,
            message.chat.id,
            granted=True,
        )
    if not linked:
        await message.answer("Tautkan akun pelanggan terlebih dahulu melalui /start link_…")
        return
    await message.answer(
        "✅ Persetujuan dicatat untuk pengingat masa sewa dan penawaran perpanjangan. "
        "Cabut kapan saja dengan /stop."
    )


@customer_router.message(Command("stop"))
async def cmd_stop(message: Message) -> None:
    if message.from_user is None or message.chat.type != "private":
        await message.answer("Perintah ini hanya tersedia melalui chat pribadi.")
        return
    with SessionLocal() as db:
        linked = TelegramService(db).record_customer_consent(
            message.from_user.id,
            message.chat.id,
            granted=False,
        )
    if not linked:
        await message.answer("Akun Telegram ini belum ditautkan ke pelanggan.")
        return
    await message.answer(
        "Persetujuan dicabut. Pengingat dan penawaran otomatis tidak akan dikirim lagi."
    )


@customer_router.message(Command("help"))
async def cmd_customer_help(message: Message) -> None:
    await message.answer(
        "<b>Perintah pelanggan</b>\n"
        "/start — tautkan akun pelanggan\n"
        "/consent — setujui pengingat dan penawaran Telegram\n"
        "/stop — cabut persetujuan dan hentikan pesan otomatis",
        parse_mode="HTML",
    )


@customer_router.callback_query(OfferSelectionCallback.filter())
async def on_offer_selected(
    query: CallbackQuery,
    callback_data: OfferSelectionCallback,
) -> None:
    if query.message is None or query.message.chat.type != "private":
        await query.answer("Respons hanya dapat diproses di chat pribadi.", show_alert=True)
        return
    try:
        offer_id = uuid.UUID(callback_data.offer_id)
        with SessionLocal() as db:
            response = TelegramService(db).respond_to_offer(
                offer_id,
                query.from_user.id,
                query.message.chat.id,
            )
    except (ValueError, BusinessRuleError) as exc:
        await query.answer(str(exc) or "Penawaran tidak valid.", show_alert=True)
        return

    await query.answer("Respons Anda sudah dicatat.")
    await query.message.answer(response)


@customer_router.callback_query(OfferDeclineCallback.filter())
async def on_offer_declined(
    query: CallbackQuery,
    callback_data: OfferDeclineCallback,
) -> None:
    if query.message is None or query.message.chat.type != "private":
        await query.answer("Respons hanya dapat diproses di chat pribadi.", show_alert=True)
        return
    try:
        offer_id = uuid.UUID(callback_data.offer_id)
        with SessionLocal() as db:
            response = TelegramService(db).decline_offer(
                offer_id,
                query.from_user.id,
                query.message.chat.id,
            )
    except (ValueError, BusinessRuleError) as exc:
        await query.answer(str(exc) or "Respons tidak valid.", show_alert=True)
        return

    await query.answer("Respons Anda sudah dicatat.")
    await query.message.answer(response)
