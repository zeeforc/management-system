"""Administrator-only Telegram dashboard and interactive creation workflows."""

import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.sql import Select

from app.core.exceptions import BusinessRuleError
from app.core.permissions import is_telegram_admin
from app.db.session import SessionLocal
from app.modules.customers.models import Customer
from app.modules.customers.schemas import CustomerCreate
from app.modules.customers.service import CustomerService
from app.modules.products.models import Product, ProductVariant
from app.modules.products.schemas import ProductCreate, ProductVariantCreate
from app.modules.products.service import ProductService
from app.modules.rentals.schemas import RentalCreate
from app.modules.rentals.service import RentalService
from app.modules.telegram.service import TelegramService
from app.shared.enums import (
    CustomerStatus,
    DurationUnit,
    ProductStatus,
    RenewalModel,
    VariantStatus,
)
from app.shared.money import DEFAULT_CURRENCY

admin_router = Router(name="telegram_admin")
PICKER_PAGE_SIZE = 8
DURATION_LABELS = {
    DurationUnit.DAYS: "hari",
    DurationUnit.WEEKS: "minggu",
    DurationUnit.MONTHS: "bulan",
    DurationUnit.YEARS: "tahun",
}


class ProductWizard(StatesGroup):
    name = State()
    category = State()
    description = State()
    image_url = State()
    profile_pin = State()
    status = State()


class VariantWizard(StatesGroup):
    product = State()
    name = State()
    duration_value = State()
    duration_unit = State()
    price = State()
    status = State()


class CustomerWizard(StatesGroup):
    display_name = State()
    username = State()
    notes = State()
    status = State()


class RentalWizard(StatesGroup):
    customer = State()
    product = State()
    variant = State()
    start_date = State()
    renewal_model = State()
    duration_value = State()
    duration_unit = State()
    price = State()
    account_email = State()
    profile = State()
    pin = State()


def _is_admin(message: Message) -> bool:
    return is_telegram_admin(message.from_user.id if message.from_user else None)


def _actor_id(message: Message) -> str:
    if message.from_user is None:
        raise BusinessRuleError("Admin Telegram user is unavailable.")
    return str(message.from_user.id)


def _is_admin_callback(query: CallbackQuery) -> bool:
    return is_telegram_admin(query.from_user.id)


def _private_callback_message(query: CallbackQuery) -> Message | None:
    message = query.message
    if isinstance(message, Message) and message.chat.type == "private":
        return message
    return None


async def _require_private_admin(message: Message) -> bool:
    if not _is_admin(message):
        await message.answer("⛔ Akses ditolak. Menu ini khusus administrator.")
        return False
    if message.chat.type != "private":
        await message.answer("🔒 Demi keamanan, gunakan alur input admin di chat pribadi bot.")
        return False
    return True


def _admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="＋ Produk", callback_data="adm:menu:add_product"),
                InlineKeyboardButton(text="＋ Varian", callback_data="adm:menu:add_variant"),
            ],
            [
                InlineKeyboardButton(text="＋ Customer", callback_data="adm:menu:add_customer"),
                InlineKeyboardButton(text="＋ Rental", callback_data="adm:menu:add_rental"),
            ],
            [
                InlineKeyboardButton(text="▦ Dashboard", callback_data="adm:menu:dashboard"),
                InlineKeyboardButton(text="◉ Katalog", callback_data="adm:menu:products"),
            ],
        ]
    )


async def _show_admin_menu(message: Message) -> None:
    await message.answer(
        "<b>⌂ Rental Management</b>\n"
        "<i>Panel operasional administrator</i>\n\n"
        "Pilih aksi. Input dan data rental hanya diproses lewat chat pribadi.",
        parse_mode="HTML",
        reply_markup=_admin_menu_keyboard(),
    )


@admin_router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    if not await _require_private_admin(message):
        return
    await state.clear()
    await _show_admin_menu(message)


def _arguments(message: Message) -> list[str]:
    return (message.text or "").split()[1:]


def _page(arguments: list[str], index: int = 0) -> int:
    try:
        return max(1, int(arguments[index]))
    except (IndexError, ValueError):
        return 1


async def _reply_admin_data(message: Message, callback) -> None:
    if not _is_admin(message):
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


def _picker_query(mode: str, product_id: str | None) -> tuple[Select[Any], str]:
    if mode in ("variant_product", "rental_product"):
        stmt: Select[Any] = select(Product).where(
            Product.archived_at.is_(None),
            Product.status == "ACTIVE",
        )
        return stmt, "products"
    if mode == "rental_customer":
        stmt = select(Customer).where(
            Customer.archived_at.is_(None),
            Customer.status == "ACTIVE",
        )
        return stmt, "customers"
    if mode == "rental_variant" and product_id:
        stmt = select(ProductVariant).where(
            ProductVariant.product_id == uuid.UUID(product_id),
            ProductVariant.archived_at.is_(None),
            ProductVariant.status == "ACTIVE",
        )
        return stmt, "variants"
    raise BusinessRuleError("Pilihan tidak valid. Mulai ulang dengan /admin.")


def _picker_callback(mode: str, item_id: uuid.UUID) -> str:
    return f"adm:pick:{mode}:{item_id}"


async def _send_picker(
    message: Message,
    state: FSMContext,
    mode: str,
    page: int = 1,
) -> None:
    data = await state.get_data()
    product_id = data.get("product_id") if mode == "rental_variant" else None
    stmt, label = _picker_query(mode, product_id)
    with SessionLocal() as db:
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = list(
            db.scalars(
                stmt.order_by(
                    Product.name if label == "products"
                    else Customer.display_name if label == "customers"
                    else ProductVariant.name
                )
                .offset((page - 1) * PICKER_PAGE_SIZE)
                .limit(PICKER_PAGE_SIZE)
            ).all()
        )

    titles = {
        "variant_product": "Pilih produk untuk varian",
        "rental_customer": "Pilih customer rental",
        "rental_product": "Pilih produk rental",
        "rental_variant": "Pilih varian produk",
    }
    rows = [
        [
            InlineKeyboardButton(
                text=(f"{item.name} · {item.category}" if isinstance(item, Product)
                      else item.display_name if isinstance(item, Customer)
                      else f"{item.name} · {item.duration_value} "
                           f"{DURATION_LABELS[item.duration_unit]}"),
                callback_data=_picker_callback(mode, item.id),
            )
        ]
        for item in items
    ]
    nav_row = []
    if page > 1:
        nav_row.append(
            InlineKeyboardButton(
                text="‹ Sebelumnya",
                callback_data=f"adm:page:{mode}:{page - 1}",
            )
        )
    if page * PICKER_PAGE_SIZE < total:
        nav_row.append(
            InlineKeyboardButton(
                text="Berikutnya ›",
                callback_data=f"adm:page:{mode}:{page + 1}",
            )
        )
    if nav_row:
        rows.append(nav_row)
    text = f"<b>{titles[mode]}</b>\nHalaman {page} · {total} pilihan"
    if not items:
        text += "\n\nBelum ada data aktif. Tambahkan data lebih dulu."
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None,
    )


async def _show_picker_from_callback(
    query: CallbackQuery,
    state: FSMContext,
    mode: str,
    page: int,
) -> None:
    if not _is_admin_callback(query):
        await query.answer("Akses ditolak.", show_alert=True)
        return
    message = _private_callback_message(query)
    if message is None:
        await query.answer("Gunakan menu admin melalui chat pribadi.", show_alert=True)
        return
    await _send_picker(message, state, mode, page)
    await query.answer()


@admin_router.callback_query(F.data.startswith("adm:menu:"))
async def on_admin_menu_action(query: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin_callback(query):
        await query.answer("Akses ditolak.", show_alert=True)
        return
    message = _private_callback_message(query)
    if message is None:
        await query.answer("Gunakan menu admin melalui chat pribadi.", show_alert=True)
        return
    action = (query.data or "").rsplit(":", maxsplit=1)[-1]
    await state.clear()
    await query.answer()
    if action == "add_product":
        await state.set_state(ProductWizard.name)
        await message.answer("◉ <b>Produk baru</b>\nKirim nama produk.", parse_mode="HTML")
    elif action == "add_variant":
        await state.set_state(VariantWizard.product)
        await _send_picker(message, state, "variant_product")
    elif action == "add_customer":
        await state.set_state(CustomerWizard.display_name)
        await message.answer(
            "♙ <b>Customer baru</b>\nKirim nama tampilan.",
            parse_mode="HTML",
        )
    elif action == "add_rental":
        await state.set_state(RentalWizard.customer)
        await _send_picker(message, state, "rental_customer")
    elif action in ("dashboard", "products"):
        with SessionLocal() as db:
            service = TelegramService(db)
            text = (
                service.format_admin_dashboard()
                if action == "dashboard"
                else service.format_products()
            )
        await message.answer(text, parse_mode="HTML")


@admin_router.callback_query(F.data.startswith("adm:page:"))
async def on_picker_page(query: CallbackQuery, state: FSMContext) -> None:
    try:
        _, _, mode, raw_page = (query.data or "").split(":")
        page = max(1, int(raw_page))
    except ValueError:
        await query.answer("Pilihan halaman tidak valid.", show_alert=True)
        return
    await _show_picker_from_callback(query, state, mode, page)


@admin_router.callback_query(F.data.startswith("adm:pick:"))
async def on_picker_item(query: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin_callback(query):
        await query.answer("Akses ditolak.", show_alert=True)
        return
    message = _private_callback_message(query)
    if message is None:
        await query.answer("Gunakan menu admin melalui chat pribadi.", show_alert=True)
        return
    try:
        _, _, mode, raw_id = (query.data or "").split(":")
        item_id = uuid.UUID(raw_id)
    except ValueError:
        await query.answer("Pilihan tidak valid.", show_alert=True)
        return
    await query.answer()

    if mode == "variant_product":
        if await state.get_state() != VariantWizard.product.state:
            await message.answer("Alur sudah kedaluwarsa. Mulai lagi dengan /admin.")
            return
        await state.update_data(product_id=str(item_id))
        await state.set_state(VariantWizard.name)
        await message.answer("Kirim nama varian.")
    elif mode == "rental_customer":
        if await state.get_state() != RentalWizard.customer.state:
            await message.answer("Alur sudah kedaluwarsa. Mulai lagi dengan /admin.")
            return
        await state.update_data(customer_id=str(item_id))
        await state.set_state(RentalWizard.product)
        await _send_picker(message, state, "rental_product")
    elif mode == "rental_product":
        if await state.get_state() != RentalWizard.product.state:
            await message.answer("Alur sudah kedaluwarsa. Mulai lagi dengan /admin.")
            return
        await state.update_data(product_id=str(item_id))
        await state.set_state(RentalWizard.variant)
        await _send_picker(message, state, "rental_variant")
    elif mode == "rental_variant":
        if await state.get_state() != RentalWizard.variant.state:
            await message.answer("Alur sudah kedaluwarsa. Mulai lagi dengan /admin.")
            return
        with SessionLocal() as db:
            variant = db.get(ProductVariant, item_id)
            product = db.get(Product, variant.product_id) if variant else None
        if variant is None or product is None:
            await message.answer("Produk/varian sudah tidak tersedia. Mulai lagi.")
            await state.clear()
            return
        await state.update_data(
            variant_id=str(variant.id),
            has_profile_pin=product.has_profile_pin,
            default_duration_value=variant.duration_value,
            default_duration_unit=str(variant.duration_unit),
            default_price=str(variant.default_price),
            currency=variant.currency,
        )
        await state.set_state(RentalWizard.start_date)
        await message.answer(
            "Kirim tanggal mulai rental dengan format <code>YYYY-MM-DD</code>.",
            parse_mode="HTML",
        )


def _choice_keyboard(prefix: str, options: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=f"{prefix}:{value}")]
            for label, value in options
        ]
    )


@admin_router.message(Command("add_product"))
async def cmd_add_product(message: Message, state: FSMContext) -> None:
    if not await _require_private_admin(message):
        return
    await state.clear()
    await state.set_state(ProductWizard.name)
    await message.answer("◉ <b>Produk baru</b>\nKirim nama produk.", parse_mode="HTML")


@admin_router.message(ProductWizard.name)
async def product_name(message: Message, state: FSMContext) -> None:
    if not await _require_private_admin(message):
        return
    name = (message.text or "").strip()
    if not name or len(name) > 160:
        await message.answer("Nama wajib diisi dan maksimal 160 karakter. Coba lagi.")
        return
    await state.update_data(name=name)
    await state.set_state(ProductWizard.category)
    await message.answer("Kirim kategori produk.")


@admin_router.message(ProductWizard.category)
async def product_category(message: Message, state: FSMContext) -> None:
    if not await _require_private_admin(message):
        return
    category = (message.text or "").strip()
    if not category or len(category) > 80:
        await message.answer("Kategori wajib diisi dan maksimal 80 karakter. Coba lagi.")
        return
    await state.update_data(category=category)
    await state.set_state(ProductWizard.description)
    await message.answer("Kirim deskripsi produk atau /skip.")


@admin_router.message(ProductWizard.description)
async def product_description(message: Message, state: FSMContext) -> None:
    if not await _require_private_admin(message):
        return
    description = (message.text or "").strip()
    await state.update_data(description=None if description == "/skip" else description)
    await state.set_state(ProductWizard.image_url)
    await message.answer("Kirim URL gambar produk atau /skip.")


@admin_router.message(ProductWizard.image_url)
async def product_image_url(message: Message, state: FSMContext) -> None:
    if not await _require_private_admin(message):
        return
    image_url = (message.text or "").strip()
    await state.update_data(image_url=None if image_url == "/skip" else image_url)
    await state.set_state(ProductWizard.profile_pin)
    await message.answer(
        "Apakah produk ini menggunakan profile dan PIN?",
        reply_markup=_choice_keyboard(
            "adm:product:profile_pin",
            [("✓ Ya", "yes"), ("Tidak", "no")],
        ),
    )


@admin_router.callback_query(F.data.startswith("adm:product:profile_pin:"))
async def product_profile_pin(query: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin_callback(query):
        await query.answer("Akses ditolak.", show_alert=True)
        return
    message = _private_callback_message(query)
    if message is None:
        await query.answer("Gunakan menu admin melalui chat pribadi.", show_alert=True)
        return
    if await state.get_state() != ProductWizard.profile_pin.state:
        await query.answer("Alur sudah kedaluwarsa.", show_alert=True)
        return
    has_profile_pin = (query.data or "").endswith(":yes")
    await state.update_data(has_profile_pin=has_profile_pin)
    await state.set_state(ProductWizard.status)
    await query.answer()
    await message.answer(
        "Pilih status produk.",
        reply_markup=_choice_keyboard(
            "adm:status:product",
            [("Aktif", ProductStatus.ACTIVE.value), ("Nonaktif", ProductStatus.INACTIVE.value)],
        ),
    )


@admin_router.message(Command("add_variant"))
async def cmd_add_variant(message: Message, state: FSMContext) -> None:
    if not await _require_private_admin(message):
        return
    await state.clear()
    await state.set_state(VariantWizard.product)
    await _send_picker(message, state, "variant_product")


@admin_router.message(VariantWizard.name)
async def variant_name(message: Message, state: FSMContext) -> None:
    if not await _require_private_admin(message):
        return
    name = (message.text or "").strip()
    if not name or len(name) > 160:
        await message.answer("Nama varian wajib diisi dan maksimal 160 karakter. Coba lagi.")
        return
    await state.update_data(name=name)
    await state.set_state(VariantWizard.duration_value)
    await message.answer("Kirim durasi varian dalam angka bulat lebih dari 0.")


@admin_router.message(VariantWizard.duration_value)
async def variant_duration_value(message: Message, state: FSMContext) -> None:
    if not await _require_private_admin(message):
        return
    try:
        value = int((message.text or "").strip())
        if value <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Durasi harus berupa angka bulat lebih dari 0. Coba lagi.")
        return
    await state.update_data(duration_value=value)
    await state.set_state(VariantWizard.duration_unit)
    await message.answer(
        "Pilih satuan durasi.",
        reply_markup=_choice_keyboard(
            "adm:unit:variant",
            [(DURATION_LABELS[unit].title(), unit.value) for unit in DurationUnit],
        ),
    )


@admin_router.message(VariantWizard.price)
async def variant_price(message: Message, state: FSMContext) -> None:
    if not await _require_private_admin(message):
        return
    try:
        price = Decimal((message.text or "").strip().replace(",", "."))
        if not price.is_finite() or price < 0:
            raise InvalidOperation
    except InvalidOperation:
        await message.answer("Harga harus angka nol atau lebih, contoh 30000. Coba lagi.")
        return
    await state.update_data(default_price=str(price))
    await state.set_state(VariantWizard.status)
    await message.answer(
        "Pilih status varian.",
        reply_markup=_choice_keyboard(
            "adm:status:variant",
            [("Aktif", VariantStatus.ACTIVE.value), ("Nonaktif", VariantStatus.INACTIVE.value)],
        ),
    )


@admin_router.message(Command("add_customer"))
async def cmd_add_customer(message: Message, state: FSMContext) -> None:
    if not await _require_private_admin(message):
        return
    await state.clear()
    await state.set_state(CustomerWizard.display_name)
    await message.answer("♙ <b>Customer baru</b>\nKirim nama tampilan.", parse_mode="HTML")


@admin_router.message(CustomerWizard.display_name)
async def customer_display_name(message: Message, state: FSMContext) -> None:
    if not await _require_private_admin(message):
        return
    name = (message.text or "").strip()
    if not name or len(name) > 160:
        await message.answer("Nama wajib diisi dan maksimal 160 karakter. Coba lagi.")
        return
    await state.update_data(display_name=name)
    await state.set_state(CustomerWizard.username)
    await message.answer("Kirim username Telegram (dengan atau tanpa @), atau /skip.")


@admin_router.message(CustomerWizard.username)
async def customer_username(message: Message, state: FSMContext) -> None:
    if not await _require_private_admin(message):
        return
    username = (message.text or "").strip()
    await state.update_data(telegram_username=None if username == "/skip" else username)
    await state.set_state(CustomerWizard.notes)
    await message.answer("Kirim catatan internal atau /skip.")


@admin_router.message(CustomerWizard.notes)
async def customer_notes(message: Message, state: FSMContext) -> None:
    if not await _require_private_admin(message):
        return
    notes = (message.text or "").strip()
    await state.update_data(internal_notes=None if notes == "/skip" else notes)
    await state.set_state(CustomerWizard.status)
    await message.answer(
        "Pilih status customer.",
        reply_markup=_choice_keyboard(
            "adm:status:customer",
            [
                ("Aktif", CustomerStatus.ACTIVE.value),
                ("Nonaktif", CustomerStatus.INACTIVE.value),
                ("Ditangguhkan", CustomerStatus.SUSPENDED.value),
            ],
        ),
    )


@admin_router.message(Command("add_rental"))
async def cmd_add_rental(message: Message, state: FSMContext) -> None:
    if not await _require_private_admin(message):
        return
    await state.clear()
    await state.set_state(RentalWizard.customer)
    await _send_picker(message, state, "rental_customer")


@admin_router.message(RentalWizard.start_date)
async def rental_start_date(message: Message, state: FSMContext) -> None:
    if not await _require_private_admin(message):
        return
    try:
        start_date = date.fromisoformat((message.text or "").strip())
    except ValueError:
        await message.answer("Format tanggal tidak valid. Gunakan YYYY-MM-DD, contoh 2026-10-27.")
        return
    await state.update_data(start_date=start_date.isoformat())
    await state.set_state(RentalWizard.renewal_model)
    await message.answer(
        "Pilih model perpanjangan rental.",
        reply_markup=_choice_keyboard(
            "adm:rental:renewal",
            [
                ("Berlanjut setelah expiry", RenewalModel.CONTINUOUS.value),
                ("Mulai langsung", RenewalModel.IMMEDIATE.value),
            ],
        ),
    )


@admin_router.message(RentalWizard.duration_value)
async def rental_duration_value(message: Message, state: FSMContext) -> None:
    if not await _require_private_admin(message):
        return
    raw_value = (message.text or "").strip()
    if raw_value == "/skip":
        await state.update_data(duration_value=None)
    else:
        try:
            value = int(raw_value)
            if value <= 0:
                raise ValueError
        except ValueError:
            await message.answer("Durasi harus angka bulat lebih dari 0, atau /skip.")
            return
        await state.update_data(duration_value=value)
    await state.set_state(RentalWizard.duration_unit)
    await message.answer(
        "Pilih satuan durasi rental.",
        reply_markup=_choice_keyboard(
            "adm:unit:rental",
            [(DURATION_LABELS[unit].title(), unit.value) for unit in DurationUnit],
        ),
    )


@admin_router.message(RentalWizard.price)
async def rental_price(message: Message, state: FSMContext) -> None:
    if not await _require_private_admin(message):
        return
    raw_price = (message.text or "").strip()
    if raw_price == "/skip":
        await state.update_data(agreed_price=None)
    else:
        try:
            price = Decimal(raw_price.replace(",", "."))
            if not price.is_finite() or price < 0:
                raise InvalidOperation
        except InvalidOperation:
            await message.answer("Harga harus angka nol atau lebih, atau /skip.")
            return
        await state.update_data(agreed_price=str(price))
    await state.set_state(RentalWizard.account_email)
    await message.answer("Kirim email akun atau /skip.")


async def _finish_rental(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    try:
        payload = RentalCreate(
            customer_id=uuid.UUID(data["customer_id"]),
            product_id=uuid.UUID(data["product_id"]),
            product_variant_id=uuid.UUID(data["variant_id"]),
            start_date=date.fromisoformat(data["start_date"]),
            duration_value=data.get("duration_value"),
            duration_unit=DurationUnit(data["duration_unit"]),
            agreed_price=data.get("agreed_price"),
            currency=data["currency"],
            renewal_model=RenewalModel(data["renewal_model"]),
            account_email=data.get("account_email"),
            profile=data.get("profile"),
            pin=data.get("pin"),
        )
        with SessionLocal() as db:
            rental = RentalService(db, actor_id=_actor_id(message)).create_rental(payload)
    except (ValidationError, BusinessRuleError, ValueError) as exc:
        await message.answer(
            f"Rental belum tersimpan: {escape(str(exc))}\n"
            "Cek pilihan dan input, lalu mulai ulang dengan /add_rental."
        )
        await state.clear()
        return
    await state.clear()
    await message.answer(
        f"✅ Rental berhasil dibuat.\n"
        f"Periode: <b>{rental.start_date:%d-%m-%Y} — {rental.expiration_date:%d-%m-%Y}</b>",
        parse_mode="HTML",
        reply_markup=_admin_menu_keyboard(),
    )


@admin_router.message(RentalWizard.account_email)
async def rental_account_email(message: Message, state: FSMContext) -> None:
    if not await _require_private_admin(message):
        return
    raw_email = (message.text or "").strip()
    await state.update_data(account_email=None if raw_email == "/skip" else raw_email)
    data = await state.get_data()
    if data["has_profile_pin"]:
        await state.set_state(RentalWizard.profile)
        await message.answer("Kirim nama profile atau /skip.")
        return
    await _finish_rental(message, state)


@admin_router.message(RentalWizard.profile)
async def rental_profile(message: Message, state: FSMContext) -> None:
    if not await _require_private_admin(message):
        return
    value = (message.text or "").strip()
    await state.update_data(profile=None if value == "/skip" else value)
    await state.set_state(RentalWizard.pin)
    await message.answer("Kirim PIN atau /skip.")


@admin_router.message(RentalWizard.pin)
async def rental_pin(message: Message, state: FSMContext) -> None:
    if not await _require_private_admin(message):
        return
    value = (message.text or "").strip()
    await state.update_data(pin=None if value == "/skip" else value)
    await _finish_rental(message, state)


@admin_router.callback_query(F.data.startswith("adm:status:"))
async def on_entity_status(query: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin_callback(query):
        await query.answer("Akses ditolak.", show_alert=True)
        return
    message = _private_callback_message(query)
    if message is None:
        await query.answer("Gunakan menu admin melalui chat pribadi.", show_alert=True)
        return
    try:
        _, _, entity, raw_status = (query.data or "").split(":")
        data = await state.get_data()
        actor_id = str(query.from_user.id)
        if entity == "product":
            if await state.get_state() != ProductWizard.status.state:
                raise BusinessRuleError("Alur sudah kedaluwarsa. Mulai lagi dengan /admin.")
            product_status = ProductStatus(raw_status)
            if product_status not in (ProductStatus.ACTIVE, ProductStatus.INACTIVE):
                raise ValueError("Invalid product status")
            with SessionLocal() as db:
                product = ProductService(db, actor_id=actor_id).create_product(
                    ProductCreate(
                        name=data["name"],
                        category=data["category"],
                        description=data.get("description"),
                        image_url=data.get("image_url"),
                        has_profile_pin=data["has_profile_pin"],
                        status=product_status,
                    )
                )
            result = f"✅ Produk <b>{escape(product.name)}</b> berhasil ditambahkan."
        elif entity == "variant":
            if await state.get_state() != VariantWizard.status.state:
                raise BusinessRuleError("Alur sudah kedaluwarsa. Mulai lagi dengan /admin.")
            variant_status = VariantStatus(raw_status)
            if variant_status not in (VariantStatus.ACTIVE, VariantStatus.INACTIVE):
                raise ValueError("Invalid variant status")
            with SessionLocal() as db:
                variant = ProductService(db, actor_id=actor_id).create_variant(
                    ProductVariantCreate(
                        product_id=uuid.UUID(data["product_id"]),
                        name=data["name"],
                        duration_value=data["duration_value"],
                        duration_unit=DurationUnit(data["duration_unit"]),
                        default_price=Decimal(data["default_price"]),
                        currency=DEFAULT_CURRENCY,
                        status=variant_status,
                    )
                )
            result = f"✅ Varian <b>{escape(variant.name)}</b> berhasil ditambahkan."
        elif entity == "customer":
            if await state.get_state() != CustomerWizard.status.state:
                raise BusinessRuleError("Alur sudah kedaluwarsa. Mulai lagi dengan /admin.")
            customer_status = CustomerStatus(raw_status)
            if customer_status == CustomerStatus.ARCHIVED:
                raise ValueError("Archived customers must be archived, not created.")
            with SessionLocal() as db:
                customer = CustomerService(db, actor_id=actor_id).create_customer(
                    CustomerCreate(
                        display_name=data["display_name"],
                        telegram_username=data.get("telegram_username"),
                        internal_notes=data.get("internal_notes"),
                        status=customer_status,
                    )
                )
            result = (
                f"✅ Customer <b>{escape(customer.display_name)}</b> berhasil ditambahkan."
            )
        else:
            raise BusinessRuleError("Pilihan status tidak valid.")
    except (ValidationError, BusinessRuleError, ValueError) as exc:
        await query.answer("Data tidak valid.", show_alert=True)
        await message.answer(f"Data belum tersimpan: {escape(str(exc))}")
        return

    await state.clear()
    await query.answer("Data tersimpan.")
    await message.answer(
        result,
        parse_mode="HTML",
        reply_markup=_admin_menu_keyboard(),
    )


@admin_router.callback_query(F.data.startswith("adm:unit:"))
async def on_duration_unit(query: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin_callback(query):
        await query.answer("Akses ditolak.", show_alert=True)
        return
    try:
        _, _, wizard, raw_unit = (query.data or "").split(":")
        unit = DurationUnit(raw_unit)
    except ValueError:
        await query.answer("Satuan durasi tidak valid.", show_alert=True)
        return
    message = _private_callback_message(query)
    if message is None:
        await query.answer("Gunakan menu admin melalui chat pribadi.", show_alert=True)
        return
    if wizard == "variant":
        if await state.get_state() != VariantWizard.duration_unit.state:
            await query.answer("Alur sudah kedaluwarsa.", show_alert=True)
            return
        await state.update_data(duration_unit=unit.value)
        await state.set_state(VariantWizard.price)
        await query.answer()
        await message.answer("Kirim harga default dalam IDR, contoh 30000.")
    elif wizard == "rental":
        if await state.get_state() != RentalWizard.duration_unit.state:
            await query.answer("Alur sudah kedaluwarsa.", show_alert=True)
            return
        await state.update_data(duration_unit=unit.value)
        data = await state.get_data()
        await state.set_state(RentalWizard.price)
        await query.answer()
        await message.answer(
            f"Kirim harga sewa atau /skip untuk memakai harga varian "
            f"({data['currency']} {data['default_price']})."
        )
    else:
        await query.answer("Pilihan tidak valid.", show_alert=True)


@admin_router.callback_query(F.data.startswith("adm:rental:renewal:"))
async def on_rental_renewal_model(query: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin_callback(query):
        await query.answer("Akses ditolak.", show_alert=True)
        return
    message = _private_callback_message(query)
    if message is None:
        await query.answer("Gunakan menu admin melalui chat pribadi.", show_alert=True)
        return
    if await state.get_state() != RentalWizard.renewal_model.state:
        await query.answer("Alur sudah kedaluwarsa.", show_alert=True)
        return
    try:
        renewal_model = RenewalModel((query.data or "").rsplit(":", maxsplit=1)[-1])
    except ValueError:
        await query.answer("Model perpanjangan tidak valid.", show_alert=True)
        return
    data = await state.get_data()
    default_unit = DurationUnit(data["default_duration_unit"])
    await state.update_data(renewal_model=renewal_model.value)
    await state.set_state(RentalWizard.duration_value)
    await query.answer()
    await message.answer(
        "Kirim durasi angka baru atau /skip untuk memakai durasi varian "
        f"({data['default_duration_value']} {DURATION_LABELS[default_unit]})."
    )


@admin_router.message(Command("help"))
async def cmd_admin_help(message: Message) -> None:
    if not _is_admin(message):
        await message.answer(
            "<b>Perintah pelanggan</b>\n"
            "/start — tautkan akun pelanggan\n"
            "/consent — setujui pengingat dan penawaran Telegram\n"
            "/rating — beri rating dan saran\n"
            "/stop — cabut persetujuan dan hentikan pesan otomatis",
            parse_mode="HTML",
        )
        return
    await message.answer(
        "<b>⌂ Menu Administrator</b>\n"
        "/admin — buka menu interaktif\n"
        "/add_product — tambah produk\n"
        "/add_variant — tambah varian\n"
        "/add_customer — tambah customer\n"
        "/add_rental — tambah rental interaktif\n"
        "/dashboard — ringkasan bisnis\n"
        "/products [halaman] — produk dan varian\n"
        "/rentals [halaman] — rental aktif\n"
        "/expiring H5|H3|H1 [halaman] — rental mendekati jatuh tempo\n"
        "/expired [halaman] — rental yang telah berakhir\n"
        "/customer &lt;nama atau username&gt; [halaman] — cari pelanggan",
        parse_mode="HTML",
        reply_markup=_admin_menu_keyboard(),
    )
