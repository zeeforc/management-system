"""Administrator-only Telegram commands with bounded, paginated database queries."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.core.permissions import is_telegram_admin
from app.db.session import SessionLocal
from app.modules.telegram.service import TelegramService

admin_router = Router(name="telegram_admin")


def _ensure_admin(message: Message) -> bool:
    user_id = message.from_user.id if message.from_user else None
    return is_telegram_admin(user_id)


def _arguments(message: Message) -> list[str]:
    return (message.text or "").split()[1:]


def _page(arguments: list[str], index: int = 0) -> int:
    try:
        return max(1, int(arguments[index]))
    except (IndexError, ValueError):
        return 1


async def _reply_admin_data(message: Message, callback) -> None:
    if not _ensure_admin(message):
        await message.answer("⛔ Akses ditolak. Perintah ini khusus administrator.")
        return
    with SessionLocal() as db:
        text = callback(TelegramService(db))
    await message.answer(text, parse_mode="HTML")


@admin_router.message(Command("dashboard"))
async def cmd_dashboard(message: Message) -> None:
    await _reply_admin_data(message, lambda service: service.format_admin_dashboard())


@admin_router.message(Command("products"))
async def cmd_products(message: Message) -> None:
    page = _page(_arguments(message))
    await _reply_admin_data(message, lambda service: service.format_products(page))


@admin_router.message(Command("rentals"))
async def cmd_rentals(message: Message) -> None:
    page = _page(_arguments(message))
    await _reply_admin_data(message, lambda service: service.format_rentals(page))


@admin_router.message(Command("expiring"))
async def cmd_expiring(message: Message) -> None:
    arguments = _arguments(message)
    stage = arguments[0].upper() if arguments else "H5"
    days_by_stage = {"H5": 5, "H-5": 5, "H3": 3, "H-3": 3, "H1": 1, "H-1": 1}
    if stage not in days_by_stage:
        await message.answer("Gunakan /expiring H5, /expiring H3, atau /expiring H1.")
        return
    page = _page(arguments, 1)
    days = days_by_stage[stage]
    await _reply_admin_data(
        message,
        lambda service: service.format_rentals(page, expiring_days=days),
    )


@admin_router.message(Command("expired"))
async def cmd_expired(message: Message) -> None:
    page = _page(_arguments(message))
    await _reply_admin_data(
        message,
        lambda service: service.format_rentals(page, expired=True),
    )


@admin_router.message(Command("customer"))
async def cmd_customer(message: Message) -> None:
    arguments = _arguments(message)
    page = _page(arguments, len(arguments) - 1) if arguments else 1
    query_arguments = arguments[:-1] if arguments and arguments[-1].isdecimal() else arguments
    query = " ".join(query_arguments)
    await _reply_admin_data(
        message,
        lambda service: service.format_customer_search(query, page),
    )


@admin_router.message(Command("help"))
async def cmd_admin_help(message: Message) -> None:
    if not _ensure_admin(message):
        await message.answer(
            "<b>Perintah pelanggan</b>\n"
            "/start — tautkan akun pelanggan\n"
            "/consent — setujui pengingat dan penawaran Telegram\n"
            "/stop — cabut persetujuan dan hentikan pesan otomatis",
            parse_mode="HTML",
        )
        return
    await message.answer(
        "<b>Perintah Administrator</b>\n"
        "/dashboard — ringkasan metrik bisnis\n"
        "/products [halaman] — produk dan varian\n"
        "/rentals [halaman] — rental aktif\n"
        "/expiring H5|H3|H1 [halaman] — rental mendekati jatuh tempo\n"
        "/expired [halaman] — rental yang telah berakhir\n"
        "/customer &lt;nama atau username&gt; [halaman] — cari pelanggan\n"
        "/help — bantuan perintah",
        parse_mode="HTML",
    )
