"""Customer QRIS renewal requests and administrator proof review."""

import logging
import uuid
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.core.config import settings
from app.core.exceptions import BusinessRuleError
from app.core.permissions import is_telegram_admin
from app.db.session import SessionLocal
from app.modules.products.models import Product, ProductVariant
from app.modules.rentals.models import Rental
from app.modules.telegram.callbacks import RenewalMonthCallback, RenewalRentalCallback
from app.modules.telegram.service import TelegramRenewalOrder, TelegramService
from app.shared.datetime_utils import current_wib_date
from app.shared.money import format_idr

renewal_router = Router(name="telegram_renewals")
logger = logging.getLogger(__name__)
MONTH_NAMES = (
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


def _format_date(value: date) -> str:
    return f"{value.day} {MONTH_NAMES[value.month - 1]} {value.year}"


def _month_keyboard(rental_id: uuid.UUID, monthly_price: Decimal) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=f"{months} bulan · {format_idr(monthly_price * months)}",
            callback_data=RenewalMonthCallback(
                rental_id=str(rental_id),
                months=months,
            ).pack(),
        )
        for months in range(1, 13)
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[buttons[index : index + 3] for index in range(0, 12, 3)]
    )


def _renewal_list(
    rows: Sequence[tuple[Rental, Product, ProductVariant]],
    rental_keyboard_rows: list[list[InlineKeyboardButton]],
) -> tuple[str, InlineKeyboardMarkup]:
    today = current_wib_date()
    lines = ["<b>Langganan yang bisa diperpanjang</b>"]
    for index, (rental, product, variant) in enumerate(rows, start=1):
        days_remaining = (rental.expiration_date - today).days
        expiry_state = (
            f"Segera habis · {days_remaining} hari"
            if 0 <= days_remaining <= 5
            else (
                f"Berakhir {_format_date(rental.expiration_date)}"
                if days_remaining >= 0
                else f"Sudah berakhir {_format_date(rental.expiration_date)}"
            )
        )
        lines.append(
            f"\n{index}. <b>{escape(product.name)}</b> · {escape(variant.name)}\n"
            f"   {escape(expiry_state)}"
        )
        button_text = f"{product.name[:32]} · {_format_date(rental.expiration_date)}"
        if 0 <= days_remaining <= 5:
            button_text = f"⏳ {button_text}"
        rental_keyboard_rows.append(
            [
                InlineKeyboardButton(
                    text=button_text[:64],
                    callback_data=RenewalRentalCallback(rental_id=str(rental.id)).pack(),
                )
            ]
        )
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rental_keyboard_rows)


@renewal_router.message(Command("perpanjang"))
async def cmd_perpanjang(message: Message, state: FSMContext) -> None:
    if message.from_user is None or message.chat.type != "private":
        await message.answer(
            "Perintah /perpanjang hanya bisa digunakan di chat pribadi dengan bot."
        )
        return
    if not is_telegram_admin(message.from_user.id):
        await state.clear()
    try:
        with SessionLocal() as db:
            rows = TelegramService(db).list_customer_renewals(
                message.from_user.id,
                message.chat.id,
            )
    except BusinessRuleError as exc:
        await message.answer(
            f"{exc}\nBuka bot dan kirim /start dengan username Telegram yang sudah dicatat admin."
        )
        return
    if not rows:
        await message.answer("Belum ada langganan yang bisa diperpanjang.")
        return

    text, keyboard = _renewal_list(rows, [])
    await message.answer(
        f"{text}\n\nPilih produk yang ingin diperpanjang:",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


@renewal_router.callback_query(RenewalRentalCallback.filter())
async def on_renewal_rental_selected(
    query: CallbackQuery,
    callback_data: RenewalRentalCallback,
) -> None:
    if query.message is None or query.message.chat.type != "private":
        await query.answer("Pilih produk melalui chat pribadi dengan bot.", show_alert=True)
        return
    try:
        rental_id = uuid.UUID(callback_data.rental_id)
        with SessionLocal() as db:
            service = TelegramService(db)
            rentals = service.list_customer_renewals(
                query.from_user.id,
                query.message.chat.id,
            )
            if not any(str(rental.id) == callback_data.rental_id for rental, _, _ in rentals):
                raise BusinessRuleError("Langganan ini tidak ditemukan untuk akun Anda.")
            pending_order = service.pending_telegram_renewal(
                rental_id,
                query.from_user.id,
                query.message.chat.id,
            )
            monthly_price = service.telegram_renewal_monthly_price(
                rental_id,
                query.from_user.id,
                query.message.chat.id,
            )
    except (ValueError, BusinessRuleError) as exc:
        await query.answer(str(exc) or "Pilihan produk tidak valid.", show_alert=True)
        return

    await query.answer()
    if pending_order is not None:
        if (
            not settings.TELEGRAM_RENEWAL_QRIS_FILE_ID
            or not settings.TELEGRAM_RENEWAL_REVIEW_GROUP_ID
        ):
            await query.message.answer("Pembayaran QRIS belum dikonfigurasi. Hubungi admin.")
            return
        try:
            await query.message.answer_photo(
                photo=settings.TELEGRAM_RENEWAL_QRIS_FILE_ID,
                caption=_payment_caption(pending_order),
            )
        except TelegramAPIError as exc:
            logger.warning(
                "QRIS for renewal %s could not be sent (%s).",
                pending_order.renewal_id,
                type(exc).__name__,
            )
            await query.message.answer("QRIS gagal dikirim. Coba lagi atau hubungi admin.")
        return
    await query.message.answer(
        "Pilih lama perpanjangan. Harga dihitung dari tarif bulanan varian produk:",
        reply_markup=_month_keyboard(rental_id, monthly_price),
    )


@renewal_router.callback_query(RenewalMonthCallback.filter())
async def on_renewal_month_selected(
    query: CallbackQuery,
    callback_data: RenewalMonthCallback,
) -> None:
    if query.message is None or query.message.chat.type != "private":
        await query.answer("Perpanjangan hanya dapat diproses lewat chat pribadi.", show_alert=True)
        return
    if not settings.TELEGRAM_RENEWAL_QRIS_FILE_ID or not settings.TELEGRAM_RENEWAL_REVIEW_GROUP_ID:
        await query.answer("Pembayaran QRIS belum dikonfigurasi. Hubungi admin.", show_alert=True)
        return
    try:
        rental_id = uuid.UUID(callback_data.rental_id)
        with SessionLocal() as db:
            order = TelegramService(db).create_telegram_renewal(
                rental_id,
                query.from_user.id,
                query.message.chat.id,
                callback_data.months,
            )
    except (ValueError, BusinessRuleError) as exc:
        await query.answer(str(exc) or "Pilihan perpanjangan tidak valid.", show_alert=True)
        return

    try:
        async with Bot(token=settings.TELEGRAM_BOT_TOKEN) as bot:
            await bot.send_photo(
                chat_id=query.message.chat.id,
                photo=settings.TELEGRAM_RENEWAL_QRIS_FILE_ID,
                caption=_payment_caption(order),
            )
    except TelegramAPIError as exc:
        logger.warning(
            "QRIS for renewal %s could not be sent (%s).",
            order.renewal_id,
            type(exc).__name__,
        )
        await query.answer("QRIS gagal dikirim. Coba lagi atau hubungi admin.", show_alert=True)
        return
    await query.answer("Detail pembayaran dikirim.")


def _payment_caption(order: TelegramRenewalOrder) -> str:
    return (
        f"Produk: {order.product_name}\n"
        f"Durasi perpanjangan: {order.duration_value} bulan\n"
        f"Periode: {_format_date(order.start_date)} – {_format_date(order.expiration_date)}\n"
        f"Nominal: {format_idr(order.amount)}\n\n"
        "Silakan transfer sesuai nominal di atas, lalu kirim screenshot bukti pembayaran "
        "ke chat ini."
    )


def _review_details(order: TelegramRenewalOrder) -> str:
    return (
        "<b>PERMINTAAN PERPANJANGAN</b>\n"
        f"Produk: <b>{escape(order.product_name)}</b>\n"
        f"Durasi: {order.duration_value} bulan\n"
        f"Periode: {_format_date(order.start_date)} – {_format_date(order.expiration_date)}\n"
        f"Nominal: <b>{escape(format_idr(order.amount))}</b>\n"
        f"Username customer: "
        f"{'@' + escape(order.username) if order.username else 'tidak tersedia'}\n\n"
        f"Email: <code>{escape(order.account_email or '—')}</code>\n"
        f"Password: <code>{escape(order.account_password or '—')}</code>\n"
        f"Profile: <code>{escape(order.profile or '—')}</code>\n"
        f"PIN: <code>{escape(order.pin or '—')}</code>"
    )


@renewal_router.message(StateFilter(None), F.photo | F.document)
async def on_renewal_payment_proof(message: Message) -> None:
    if message.from_user is None or message.chat.type != "private":
        return
    if message.document is not None and not (
        message.document.mime_type and message.document.mime_type.startswith("image/")
    ):
        await message.answer("Kirim bukti pembayaran berupa gambar.")
        return
    if not settings.TELEGRAM_RENEWAL_REVIEW_GROUP_ID:
        await message.answer("Grup verifikasi belum dikonfigurasi. Hubungi admin.")
        return
    try:
        with SessionLocal() as db:
            order = TelegramService(db).renewal_for_proof(
                message.from_user.id,
                message.chat.id,
            )
    except BusinessRuleError as exc:
        await message.answer(str(exc))
        return

    try:
        async with Bot(token=settings.TELEGRAM_BOT_TOKEN) as bot:
            forwarded = await bot.copy_message(
                chat_id=settings.TELEGRAM_RENEWAL_REVIEW_GROUP_ID,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
                caption=f"Bukti pembayaran perpanjangan · {order.renewal_id}",
            )
            await bot.send_message(
                chat_id=settings.TELEGRAM_RENEWAL_REVIEW_GROUP_ID,
                text=_review_details(order),
                parse_mode="HTML",
                reply_to_message_id=forwarded.message_id,
            )
        with SessionLocal() as db:
            TelegramService(db).record_renewal_proof_message(
                order.renewal_id,
                settings.TELEGRAM_RENEWAL_REVIEW_GROUP_ID,
                forwarded.message_id,
            )
    except (TelegramAPIError, BusinessRuleError) as exc:
        logger.warning(
            "Payment proof for renewal %s was not fully submitted (%s).",
            order.renewal_id,
            type(exc).__name__,
        )
        await message.answer(
            "Bukti belum berhasil diteruskan ke admin. Silakan coba kirim ulang atau hubungi admin."
        )
        return

    await message.answer("Pesanan kamu telah kami terima, menunggu konfirmasi admin.")


def _admin_review_target(message: Message) -> int | None:
    if not is_telegram_admin(message.from_user.id if message.from_user else None):
        return None
    if (
        settings.TELEGRAM_RENEWAL_REVIEW_GROUP_ID is None
        or message.chat.id != settings.TELEGRAM_RENEWAL_REVIEW_GROUP_ID
    ):
        return None
    if message.reply_to_message is None:
        return None
    return message.reply_to_message.message_id


@renewal_router.message(Command("done"))
async def cmd_renewal_done(message: Message) -> None:
    if message.from_user is None or not is_telegram_admin(message.from_user.id):
        await message.answer("Perintah ini khusus admin.")
        return
    telegram_admin_id = message.from_user.id
    review_message_id = _admin_review_target(message)
    if review_message_id is None:
        await message.answer("Balas foto bukti pembayaran di grup verifikasi dengan /done.")
        return
    try:
        with SessionLocal() as db:
            order, completed_now = TelegramService(db).complete_telegram_renewal(
                message.chat.id,
                review_message_id,
                telegram_admin_id,
            )
    except BusinessRuleError as exc:
        await message.answer(str(exc))
        return

    status_text = "Perpanjangan selesai dan dashboard telah diperbarui."
    if not completed_now:
        status_text = "Perpanjangan ini sebelumnya sudah selesai."
    await message.answer(status_text)
    try:
        async with Bot(token=settings.TELEGRAM_BOT_TOKEN) as bot:
            await bot.send_message(
                chat_id=order.chat_id,
                text=(
                    f"✅ Perpanjangan {order.product_name} telah dikonfirmasi selesai.\n"
                    f"Masa aktif sampai {_format_date(order.expiration_date)}."
                ),
            )
    except TelegramAPIError as exc:
        logger.warning(
            "Customer update for completed renewal %s could not be sent (%s).",
            order.renewal_id,
            type(exc).__name__,
        )


@renewal_router.message(Command("resend"))
async def cmd_renewal_resend(message: Message) -> None:
    if message.from_user is None or not is_telegram_admin(message.from_user.id):
        await message.answer("Perintah ini khusus admin.")
        return
    review_message_id = _admin_review_target(message)
    if review_message_id is None:
        await message.answer("Balas foto bukti pembayaran di grup verifikasi dengan /resend.")
        return
    try:
        with SessionLocal() as db:
            order = TelegramService(db).resend_renewal_proof(
                message.chat.id,
                review_message_id,
            )
    except BusinessRuleError as exc:
        await message.answer(str(exc))
        return

    try:
        async with Bot(token=settings.TELEGRAM_BOT_TOKEN) as bot:
            await bot.send_message(
                chat_id=order.chat_id,
                text="Bukti pembayaran perlu dikirim ulang dengan gambar yang lebih jelas.",
            )
    except TelegramAPIError as exc:
        logger.warning(
            "Resend request for renewal %s could not be delivered (%s).",
            order.renewal_id,
            type(exc).__name__,
        )
        await message.answer("Status direset, tetapi pesan ke customer gagal dikirim.")
        return
    await message.answer("Customer diminta mengirim ulang bukti pembayaran.")
