"""Customer Telegram linking, consent, and renewal-offer callbacks."""

import logging
import uuid
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.core.config import settings
from app.core.exceptions import BusinessRuleError
from app.core.permissions import is_telegram_admin
from app.db.session import SessionLocal
from app.modules.customers.models import StoreFeedback
from app.modules.telegram.callbacks import OfferDeclineCallback, OfferSelectionCallback
from app.modules.telegram.service import TelegramService

customer_router = Router(name="telegram_customer")
logger = logging.getLogger(__name__)


class FeedbackWizard(StatesGroup):
    comment = State()


def _rating_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{rating} ★",
                    callback_data=f"customer:rating:{rating}",
                )
                for rating in range(1, 6)
            ]
        ]
    )


@customer_router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    sender = message.from_user
    if sender is None or message.chat.type != "private":
        await message.answer("Tautkan akun melalui chat pribadi dengan bot ini.")
        return
    if is_telegram_admin(sender.id):
        await message.answer(
            "<b>⌂ Rental Management</b>\n"
            "<i>Panel operasional administrator</i>\n\n"
            "Ketik /admin untuk membuka menu interaktif.",
            parse_mode="HTML",
        )
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
            "Kirim /stop kapan saja untuk mencabut persetujuan. "
            "Ketik /rating untuk memberi rating dan saran toko."
        )
        return

    await message.answer(
        "👋 Selamat datang di Bot Rental Monitoring.\n"
        "Minta tautan akun dari admin, lalu buka tautan tersebut melalui chat pribadi "
        "dengan bot ini. Gunakan /help untuk melihat perintah pelanggan."
    )


@customer_router.message(Command("rating"))
async def cmd_rating(message: Message, state: FSMContext) -> None:
    if message.from_user is None or message.chat.type != "private":
        await message.answer("Rating hanya dapat dikirim melalui chat pribadi dengan bot.")
        return
    with SessionLocal() as db:
        customer_name = TelegramService(db).linked_customer_display_name(
            message.from_user.id,
            message.chat.id,
        )
    if customer_name is None:
        await message.answer("Tautkan akun pelanggan terlebih dahulu melalui /start link_…")
        return
    await state.clear()
    await message.answer(
        "⭐ <b>Bagaimana pengalamanmu?</b>\n"
        "Pilih rating 1 sampai 5. Nama tampilan dan saran yang kamu kirim akan "
        "dipublikasikan di channel ulasan toko.",
        parse_mode="HTML",
        reply_markup=_rating_keyboard(),
    )


@customer_router.callback_query(F.data.startswith("customer:rating:"))
async def on_rating_selected(query: CallbackQuery, state: FSMContext) -> None:
    if query.message is None or query.message.chat.type != "private":
        await query.answer("Rating hanya dapat dikirim lewat chat pribadi.", show_alert=True)
        return
    try:
        rating = int((query.data or "").rsplit(":", maxsplit=1)[-1])
        if not 1 <= rating <= 5:
            raise ValueError
    except ValueError:
        await query.answer("Rating tidak valid.", show_alert=True)
        return
    with SessionLocal() as db:
        customer_name = TelegramService(db).linked_customer_display_name(
            query.from_user.id,
            query.message.chat.id,
        )
    if customer_name is None:
        await query.answer("Tautkan akun pelanggan terlebih dahulu.", show_alert=True)
        return
    await state.update_data(rating=rating)
    await state.set_state(FeedbackWizard.comment)
    await query.answer("Rating dipilih.")
    await query.message.answer("Tulis masukan/saran, atau kirim /skip untuk melewati.")


@customer_router.message(FeedbackWizard.comment)
async def on_feedback_comment(message: Message, state: FSMContext) -> None:
    if message.from_user is None or message.chat.type != "private":
        await message.answer("Masukan hanya dapat dikirim melalui chat pribadi.")
        return
    comment = (message.text or "").strip()
    if comment != "/skip" and len(comment) > 1000:
        await message.answer("Masukan maksimal 1.000 karakter. Silakan ringkas dan kirim ulang.")
        return
    data = await state.get_data()
    content = None if comment == "/skip" or not comment else comment
    try:
        with SessionLocal() as db:
            feedback_id, customer_name = TelegramService(db).create_store_feedback(
                message.from_user.id,
                message.chat.id,
                int(data["rating"]),
                content,
            )
    except BusinessRuleError as exc:
        await state.clear()
        await message.answer(str(exc))
        return
    await state.clear()

    channel_id = settings.TELEGRAM_FEEDBACK_CHANNEL_ID
    if not channel_id:
        await message.answer(
            "✅ Terima kasih! Rating dan masukanmu sudah tersimpan. "
            "Channel ulasan belum dikonfigurasi, jadi belum dipublikasikan."
        )
        return

    rating = int(data["rating"])
    stars = "★" * rating + "☆" * (5 - rating)
    channel_text = (
        f"⭐ <b>Ulasan Toko · {rating}/5</b>\n"
        f"{stars}\n\n"
        f"👤 Oleh: <b>{escape(customer_name)}</b>\n"
        f"💬 Saran: {escape(content) if content else '—'}"
    )
    try:
        async with Bot(token=settings.TELEGRAM_BOT_TOKEN) as bot:
            sent_message = await bot.send_message(
                chat_id=channel_id,
                text=channel_text,
                parse_mode="HTML",
            )
        with SessionLocal() as db:
            feedback = db.get(StoreFeedback, feedback_id)
            if feedback is not None:
                feedback.channel_message_id = sent_message.message_id
                db.commit()
    except TelegramAPIError as exc:
        logger.warning(
            "Feedback %s was saved but could not be published "
            "to the configured Telegram channel (%s).",
            feedback_id,
            type(exc).__name__,
        )
        await message.answer(
            "✅ Rating tersimpan, tetapi belum berhasil dipublikasikan ke channel. "
            "Silakan hubungi admin agar dapat ditindaklanjuti."
        )
        return
    await message.answer("✅ Terima kasih! Ulasanmu berhasil dikirim ke channel toko.")


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
        "/rating — beri rating dan saran untuk toko\n"
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
