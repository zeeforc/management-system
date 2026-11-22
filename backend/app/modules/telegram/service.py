"""Telegram-facing workflows shared with the application's database services."""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from html import escape

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, with_loader_criteria
from sqlalchemy.sql.elements import ColumnElement

from app.core.encryption import decrypt_credential
from app.core.exceptions import BusinessRuleError
from app.core.security import hash_token
from app.modules.customers.models import (
    Customer,
    NotificationConsent,
    StoreFeedback,
    TelegramLinkToken,
)
from app.modules.customers.service import ensure_initial_telegram_consents
from app.modules.notifications.models import NotificationResponse
from app.modules.payments.models import Payment
from app.modules.products.models import Product, ProductVariant
from app.modules.renewals.models import RenewalOffer, RentalRenewal
from app.modules.renewals.service import RenewalService
from app.modules.rentals.models import Rental
from app.modules.reports.schemas import DashboardSummaryRead
from app.modules.reports.service import ReportService
from app.shared.datetime_utils import (
    calculate_expiration_date,
    calculate_renewal_dates,
    current_wib_date,
    utc_now,
)
from app.shared.enums import (
    ConsentStatus,
    ConsentType,
    CustomerResponseType,
    CustomerStatus,
    DurationUnit,
    PaymentMethod,
    PaymentStatus,
    RenewalModel,
    RenewalOfferStatus,
    RenewalStatus,
    RentalStatus,
)
from app.shared.money import format_idr, normalize_money, validate_currency

PAGE_SIZE = 10


@dataclass(frozen=True)
class TelegramRenewalOrder:
    renewal_id: uuid.UUID
    chat_id: int
    customer_name: str
    username: str | None
    product_name: str
    duration_value: int
    start_date: date
    expiration_date: date
    amount: Decimal
    currency: str
    account_email: str | None
    account_password: str | None
    profile: str | None
    pin: str | None


class TelegramService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.report_service = ReportService(db)

    def linked_customer_display_name(
        self,
        telegram_user_id: int,
        telegram_chat_id: int,
    ) -> str | None:
        customer = self.db.scalar(
            select(Customer).where(
                Customer.telegram_user_id == telegram_user_id,
                Customer.telegram_chat_id == telegram_chat_id,
                Customer.archived_at.is_(None),
                Customer.status == CustomerStatus.ACTIVE,
            )
        )
        return customer.display_name if customer is not None else None

    def format_admin_dashboard(self) -> str:
        summary: DashboardSummaryRead = self.report_service.get_dashboard_summary()
        return (
            f"📊 <b>RINGKASAN BISNIS</b>\n"
            f"<i>Data per {summary.wib_reference_date}</i>\n\n"
            f"📦 <b>Katalog</b>\n"
            f"   Produk: <code>{summary.total_products}</code> · "
            f"Varian aktif: <code>{summary.total_active_variants}</code>\n"
            f"👥 <b>Pelanggan</b>\n"
            f"   Total: <code>{summary.total_customers}</code>\n"
            f"🗓 <b>Masa sewa</b>\n"
            f"   Aktif: <code>{summary.active_rentals}</code>\n"
            f"   Jatuh tempo H-5 / H-3 / H-1: "
            f"<code>{summary.rentals_expiring_in_5_days}/"
            f"{summary.rentals_expiring_in_3_days}/"
            f"{summary.rentals_expiring_tomorrow}</code>\n"
            f"   Expired: <code>{summary.expired_rentals}</code>\n\n"
            f"🔄 <b>Renewal & pembayaran</b>\n"
            f"   Permintaan pending: <code>{summary.pending_renewal_requests}</code>\n"
            f"   Menunggu verifikasi: "
            f"<code>{summary.pending_payment_verifications}</code>\n"
            f"   Terverifikasi: "
            f"<code>{escape(format_idr(summary.verified_payment_totals))}</code>\n\n"
            f"🔔 Notifikasi perlu perhatian: <code>{summary.failed_notifications}</code>"
        )

    def format_products(self, page: int = 1) -> str:
        stmt = (
            select(Product)
            .options(
                with_loader_criteria(
                    ProductVariant,
                    ProductVariant.archived_at.is_(None),
                    include_aliases=True,
                )
            )
            .where(Product.archived_at.is_(None))
            .order_by(Product.name)
        )
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        products = list(self.db.scalars(stmt.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)).all())
        if not products:
            return "Belum ada produk pada halaman ini."
        lines = [f"📦 <b>KATALOG PRODUK</b>\n<i>Halaman {page} · {total} produk</i>\n"]
        for product in products:
            lines.append(
                f"▫️ <b>{escape(product.name)}</b> · {escape(product.status)}\n"
                f"   Kategori: {escape(product.category)}"
            )
            for variant in sorted(product.variants, key=lambda item: item.name):
                lines.append(
                    f"   └ {escape(variant.name)} · "
                    f"{variant.duration_value} {escape(variant.duration_unit.lower())}, "
                    f"{escape(format_idr(variant.default_price))}"
                )
            lines.append("")
        return "\n".join(lines) + self._page_hint(page, total)

    def format_rentals(
        self,
        page: int = 1,
        *,
        expiring_days: int | None = None,
        expired: bool = False,
    ) -> str:
        today = current_wib_date()
        stmt = (
            select(Rental, Customer, Product, ProductVariant)
            .join(Customer, Customer.id == Rental.customer_id)
            .join(Product, Product.id == Rental.product_id)
            .join(ProductVariant, ProductVariant.id == Rental.product_variant_id)
            .where(
                Rental.archived_at.is_(None),
                Rental.status != RentalStatus.CANCELLED,
            )
        )
        if expiring_days is not None:
            stmt = stmt.where(Rental.expiration_date == today + timedelta(days=expiring_days))
        elif expired:
            stmt = stmt.where(Rental.expiration_date < today)
        else:
            stmt = stmt.where(
                Rental.start_date <= today,
                Rental.expiration_date >= today,
            )

        total = (
            self.db.scalar(
                select(func.count()).select_from(stmt.with_only_columns(Rental.id).subquery())
            )
            or 0
        )
        rows = self.db.execute(
            stmt.order_by(Rental.expiration_date).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
        ).all()
        if not rows:
            return "Tidak ada rental yang cocok pada halaman ini."

        title = (
            "Sewa expired"
            if expired
            else (f"Sewa jatuh tempo H-{expiring_days}" if expiring_days else "Sewa aktif")
        )
        lines = [f"🗓 <b>{title.upper()}</b>\n<i>Halaman {page} · {total} rental</i>\n"]
        for rental, customer, product, variant in rows:
            username = (
                f"@{escape(customer.telegram_username)}"
                if customer.telegram_username
                else "username belum dicatat"
            )
            lines.append(
                f"👤 <b>{escape(customer.display_name)}</b>\n"
                f"   Telegram: {username}\n"
                f"🎬 {escape(product.name)} · {escape(variant.name)}\n"
                f"   Berakhir: <b>{rental.expiration_date:%d %b %Y}</b>\n"
                f"   Harga: {escape(format_idr(rental.agreed_price))}\n"
            )
        return "\n".join(lines) + self._page_hint(page, total)

    def format_customer_search(self, query: str, page: int = 1) -> str:
        search = query.strip()
        if not search:
            return "Gunakan <code>/customer nama-atau-username [halaman]</code>."

        conditions: list[ColumnElement[bool]] = [
            Customer.display_name.ilike(f"%{search}%"),
            Customer.telegram_username.ilike(f"%{search.lstrip('@')}%"),
        ]
        if search.isdecimal():
            conditions.append(Customer.telegram_user_id == int(search))

        stmt = select(Customer).where(
            Customer.archived_at.is_(None),
            or_(*conditions),
        )
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        customers = list(
            self.db.scalars(
                stmt.order_by(Customer.display_name).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
            ).all()
        )
        if not customers:
            return "Pelanggan tidak ditemukan."
        lines = [f"👥 <b>HASIL PENCARIAN PELANGGAN</b>\n<i>Halaman {page} · {total} cocok</i>\n"]
        for customer in customers:
            username = (
                f"@{escape(customer.telegram_username)}" if customer.telegram_username else "—"
            )
            chat_state = "terhubung" if customer.telegram_chat_id is not None else "belum terhubung"
            lines.append(
                f"👤 <b>{escape(customer.display_name)}</b> · {escape(customer.status)}\n"
                f"   Username: {username}\n"
                f"   Akun Telegram: {chat_state}\n"
            )
        return "\n".join(lines) + self._page_hint(page, total)

    @staticmethod
    def _page_hint(page: int, total: int) -> str:
        if page * PAGE_SIZE < total:
            return f"\n\nHalaman berikutnya: <code>{page + 1}</code>."
        return ""

    def link_customer(
        self,
        raw_token: str,
        telegram_user_id: int,
        telegram_chat_id: int,
        username: str | None,
    ) -> str:
        token = self.db.scalar(
            select(TelegramLinkToken)
            .where(TelegramLinkToken.token_hash == hash_token(raw_token))
            .with_for_update()
        )
        if token is None or token.used_at is not None or token.expires_at <= utc_now():
            raise BusinessRuleError("Tautan tidak valid atau sudah kedaluwarsa.")
        customer = self.db.scalar(
            select(Customer).where(Customer.id == token.customer_id).with_for_update()
        )
        if (
            customer is None
            or customer.archived_at is not None
            or customer.status != CustomerStatus.ACTIVE
        ):
            raise BusinessRuleError("Akun pelanggan tidak aktif.")
        linked_user = self.db.scalar(
            select(Customer).where(
                Customer.telegram_user_id == telegram_user_id,
                Customer.id != customer.id,
            )
        )
        linked_chat = self.db.scalar(
            select(Customer).where(
                Customer.telegram_chat_id == telegram_chat_id,
                Customer.id != customer.id,
            )
        )
        if linked_user is not None or linked_chat is not None:
            raise BusinessRuleError("Akun Telegram ini sudah ditautkan ke pelanggan lain.")

        customer.telegram_user_id = telegram_user_id
        customer.telegram_chat_id = telegram_chat_id
        customer.telegram_username = username
        token.used_at = utc_now()
        ensure_initial_telegram_consents(self.db, customer.id)
        self.db.commit()
        return customer.display_name

    def link_customer_by_username(
        self,
        telegram_user_id: int,
        telegram_chat_id: int,
        username: str | None,
    ) -> str | None:
        if not username:
            return None
        matches = list(
            self.db.scalars(
                select(Customer)
                .where(
                    func.lower(Customer.telegram_username) == username.lower(),
                    Customer.archived_at.is_(None),
                    Customer.status == CustomerStatus.ACTIVE,
                )
                .with_for_update()
                .limit(2)
            ).all()
        )
        if not matches:
            return None
        if len(matches) > 1:
            raise BusinessRuleError(
                "Username Telegram ini terdaftar pada lebih dari satu customer."
            )
        customer = matches[0]
        if customer.telegram_user_id not in (None, telegram_user_id):
            raise BusinessRuleError(
                "Username ini sudah terhubung ke akun Telegram lain. Hubungi admin."
            )
        linked_user = self.db.scalar(
            select(Customer.id).where(
                Customer.telegram_user_id == telegram_user_id,
                Customer.id != customer.id,
            )
        )
        linked_chat = self.db.scalar(
            select(Customer.id).where(
                Customer.telegram_chat_id == telegram_chat_id,
                Customer.id != customer.id,
            )
        )
        if linked_user is not None or linked_chat is not None:
            raise BusinessRuleError("Akun Telegram ini sudah ditautkan ke customer lain.")

        customer.telegram_user_id = telegram_user_id
        customer.telegram_chat_id = telegram_chat_id
        customer.telegram_username = username
        ensure_initial_telegram_consents(self.db, customer.id)
        self.db.commit()
        return customer.display_name

    def list_customer_renewals(
        self,
        telegram_user_id: int,
        telegram_chat_id: int,
    ) -> list[tuple[Rental, Product, ProductVariant]]:
        customer = self.db.scalar(
            select(Customer).where(
                Customer.telegram_user_id == telegram_user_id,
                Customer.telegram_chat_id == telegram_chat_id,
                Customer.archived_at.is_(None),
                Customer.status == CustomerStatus.ACTIVE,
            )
        )
        if customer is None:
            raise BusinessRuleError("Akun Telegram pelanggan belum terhubung.")
        rows = list(
            self.db.execute(
                select(Rental, Product, ProductVariant)
                .join(Product, Product.id == Rental.product_id)
                .join(ProductVariant, ProductVariant.id == Rental.product_variant_id)
                .where(
                    Rental.customer_id == customer.id,
                    Rental.archived_at.is_(None),
                    Rental.status != RentalStatus.CANCELLED,
                )
            ).all()
        )
        today = current_wib_date()

        def sort_key(row: tuple[Rental, Product, ProductVariant]) -> tuple[int, int]:
            days_remaining = (row[0].expiration_date - today).days
            if 0 <= days_remaining <= 5:
                return (0, days_remaining)
            if days_remaining > 5:
                return (1, days_remaining)
            return (2, -days_remaining)

        return sorted(rows, key=sort_key)

    def pending_telegram_renewal(
        self,
        rental_id: uuid.UUID,
        telegram_user_id: int,
        telegram_chat_id: int,
    ) -> TelegramRenewalOrder | None:
        customer = self.db.scalar(
            select(Customer).where(
                Customer.telegram_user_id == telegram_user_id,
                Customer.telegram_chat_id == telegram_chat_id,
                Customer.archived_at.is_(None),
                Customer.status == CustomerStatus.ACTIVE,
            )
        )
        if customer is None:
            raise BusinessRuleError("Akun Telegram pelanggan belum terhubung.")
        renewal = self.db.scalar(
            select(RentalRenewal)
            .join(Rental, Rental.id == RentalRenewal.rental_id)
            .where(
                Rental.id == rental_id,
                Rental.customer_id == customer.id,
                RentalRenewal.status == RenewalStatus.PENDING,
            )
            .order_by(RentalRenewal.created_at.desc())
            .limit(1)
        )
        if renewal is None:
            return None
        if renewal.telegram_review_message_id is not None:
            raise BusinessRuleError(
                "Bukti pembayaran sudah dikirim. Mohon tunggu konfirmasi admin."
            )
        return self._renewal_order(renewal.id)

    def telegram_renewal_monthly_price(
        self,
        rental_id: uuid.UUID,
        telegram_user_id: int,
        telegram_chat_id: int,
    ) -> Decimal:
        customer = self.db.scalar(
            select(Customer).where(
                Customer.telegram_user_id == telegram_user_id,
                Customer.telegram_chat_id == telegram_chat_id,
                Customer.archived_at.is_(None),
                Customer.status == CustomerStatus.ACTIVE,
            )
        )
        if customer is None:
            raise BusinessRuleError("Akun Telegram pelanggan belum terhubung.")
        rental = self.db.scalar(
            select(Rental).where(
                Rental.id == rental_id,
                Rental.customer_id == customer.id,
                Rental.archived_at.is_(None),
                Rental.status != RentalStatus.CANCELLED,
            )
        )
        if rental is None:
            raise BusinessRuleError("Langganan ini tidak ditemukan untuk akun Anda.")
        variant = self.db.get(ProductVariant, rental.product_variant_id)
        if variant is None:
            raise BusinessRuleError("Varian produk tidak ditemukan.")
        return self._variant_monthly_price(variant)

    def create_telegram_renewal(
        self,
        rental_id: uuid.UUID,
        telegram_user_id: int,
        telegram_chat_id: int,
        months: int,
    ) -> TelegramRenewalOrder:
        if not 1 <= months <= 12:
            raise BusinessRuleError("Durasi perpanjangan harus antara 1 sampai 12 bulan.")
        customer = self.db.scalar(
            select(Customer).where(
                Customer.telegram_user_id == telegram_user_id,
                Customer.telegram_chat_id == telegram_chat_id,
                Customer.archived_at.is_(None),
                Customer.status == CustomerStatus.ACTIVE,
            )
        )
        if customer is None:
            raise BusinessRuleError("Akun Telegram pelanggan belum terhubung.")
        rental = self.db.scalar(
            select(Rental)
            .where(
                Rental.id == rental_id,
                Rental.customer_id == customer.id,
                Rental.archived_at.is_(None),
                Rental.status != RentalStatus.CANCELLED,
            )
            .with_for_update()
        )
        if rental is None:
            raise BusinessRuleError("Langganan tidak ditemukan atau tidak dapat diperpanjang.")

        existing = self.db.scalar(
            select(RentalRenewal)
            .where(
                RentalRenewal.rental_id == rental.id,
                RentalRenewal.status == RenewalStatus.PENDING,
                RentalRenewal.id.in_(
                    select(Payment.renewal_id).where(
                        Payment.rental_id == rental.id,
                        Payment.status == PaymentStatus.PENDING,
                        Payment.payment_reference.like("Telegram renewal %"),
                    )
                ),
            )
            .order_by(RentalRenewal.created_at.desc())
            .limit(1)
            .with_for_update()
        )
        if existing is not None:
            if existing.duration_value != months or existing.duration_unit != DurationUnit.MONTHS:
                raise BusinessRuleError(
                    "Sudah ada permintaan perpanjangan yang menunggu untuk langganan ini."
                )
            if existing.telegram_review_message_id is not None:
                raise BusinessRuleError(
                    "Bukti pembayaran sudah diterima dan sedang menunggu konfirmasi admin."
                )
            return self._renewal_order(existing.id)

        variant = self.db.get(ProductVariant, rental.product_variant_id)
        if variant is None:
            raise BusinessRuleError("Varian produk tidak ditemukan.")
        monthly_price = self._variant_monthly_price(variant)
        amount = normalize_money(monthly_price * months, variant.currency)
        today = current_wib_date()
        expired = rental.expiration_date < today
        renewal_model = RenewalModel.IMMEDIATE if expired else RenewalModel.CONTINUOUS
        new_start_date = today if expired else rental.expiration_date + timedelta(days=1)
        new_expiration_date = calculate_expiration_date(
            new_start_date,
            months,
            DurationUnit.MONTHS,
        )
        renewal = RentalRenewal(
            rental_id=rental.id,
            previous_start_date=rental.start_date,
            previous_expiration_date=rental.expiration_date,
            new_start_date=new_start_date,
            new_expiration_date=new_expiration_date,
            duration_value=months,
            duration_unit=DurationUnit.MONTHS,
            renewal_model=renewal_model,
            agreed_price=amount,
            currency=validate_currency(variant.currency),
            status=RenewalStatus.PENDING,
        )
        self.db.add(renewal)
        self.db.flush()
        self.db.add(
            Payment(
                customer_id=customer.id,
                rental_id=rental.id,
                renewal_id=renewal.id,
                amount=amount,
                currency=renewal.currency,
                payment_method=PaymentMethod.QRIS,
                status=PaymentStatus.PENDING,
                payment_reference=f"Telegram renewal {renewal.id}",
            )
        )
        self.db.commit()
        return self._renewal_order(renewal.id)

    @staticmethod
    def _variant_monthly_price(variant: ProductVariant) -> Decimal:
        duration_value = Decimal(variant.duration_value)
        if variant.duration_unit == DurationUnit.MONTHS:
            months = duration_value
        elif variant.duration_unit == DurationUnit.YEARS:
            months = duration_value * 12
        elif variant.duration_unit == DurationUnit.WEEKS:
            months = duration_value * 7 / 30
        elif variant.duration_unit == DurationUnit.DAYS:
            months = duration_value / 30
        else:
            raise BusinessRuleError("Satuan durasi varian tidak didukung.")
        return (Decimal(variant.default_price) / months).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )

    def _renewal_order(self, renewal_id: uuid.UUID) -> TelegramRenewalOrder:
        row = self.db.execute(
            select(RentalRenewal, Rental, Customer, Product).join(
                Rental, Rental.id == RentalRenewal.rental_id
            ).join(
                Customer, Customer.id == Rental.customer_id
            ).join(
                Product, Product.id == Rental.product_id
            ).where(RentalRenewal.id == renewal_id)
        ).one_or_none()
        if row is None:
            raise BusinessRuleError("Permintaan perpanjangan tidak ditemukan.")
        renewal, rental, customer, product = row
        if customer.telegram_chat_id is None:
            raise BusinessRuleError("Chat Telegram customer tidak tersedia.")
        return TelegramRenewalOrder(
            renewal_id=renewal.id,
            chat_id=customer.telegram_chat_id,
            customer_name=customer.display_name,
            username=customer.telegram_username,
            product_name=product.name,
            duration_value=renewal.duration_value,
            start_date=renewal.new_start_date,
            expiration_date=renewal.new_expiration_date,
            amount=renewal.agreed_price,
            currency=renewal.currency,
            account_email=decrypt_credential(rental.account_email_encrypted),
            account_password=decrypt_credential(rental.account_password_encrypted),
            profile=decrypt_credential(rental.profile_encrypted),
            pin=decrypt_credential(rental.pin_encrypted),
        )

    def renewal_for_proof(
        self,
        telegram_user_id: int,
        telegram_chat_id: int,
    ) -> TelegramRenewalOrder:
        customer = self.db.scalar(
            select(Customer).where(
                Customer.telegram_user_id == telegram_user_id,
                Customer.telegram_chat_id == telegram_chat_id,
                Customer.archived_at.is_(None),
                Customer.status == CustomerStatus.ACTIVE,
            )
        )
        if customer is None:
            raise BusinessRuleError("Akun Telegram pelanggan belum terhubung.")
        renewal = self.db.scalar(
            select(RentalRenewal)
            .join(Rental, Rental.id == RentalRenewal.rental_id)
            .where(
                Rental.customer_id == customer.id,
                RentalRenewal.status == RenewalStatus.PENDING,
                RentalRenewal.id.in_(
                    select(Payment.renewal_id).where(
                        Payment.customer_id == customer.id,
                        Payment.status == PaymentStatus.PENDING,
                        Payment.payment_reference.like("Telegram renewal %"),
                    )
                ),
            )
            .order_by(RentalRenewal.created_at.desc())
            .limit(1)
            .with_for_update()
        )
        if renewal is None:
            raise BusinessRuleError("Tidak ada permintaan perpanjangan yang menunggu bukti.")
        if renewal.telegram_review_message_id is not None:
            raise BusinessRuleError("Bukti pembayaran sudah diterima dan sedang menunggu admin.")
        return self._renewal_order(renewal.id)

    def record_renewal_proof_message(
        self,
        renewal_id: uuid.UUID,
        group_chat_id: int,
        message_id: int,
    ) -> None:
        renewal = self.db.scalar(
            select(RentalRenewal)
            .where(
                RentalRenewal.id == renewal_id,
                RentalRenewal.status == RenewalStatus.PENDING,
                RentalRenewal.telegram_review_message_id.is_(None),
            )
            .with_for_update()
        )
        if renewal is None:
            raise BusinessRuleError("Permintaan ini sudah berubah; bukti tidak dapat ditautkan.")
        renewal.telegram_review_chat_id = group_chat_id
        renewal.telegram_review_message_id = message_id
        self.db.commit()

    def resend_renewal_proof(self, group_chat_id: int, message_id: int) -> TelegramRenewalOrder:
        renewal = self.db.scalar(
            select(RentalRenewal)
            .where(
                RentalRenewal.telegram_review_chat_id == group_chat_id,
                RentalRenewal.telegram_review_message_id == message_id,
                RentalRenewal.status == RenewalStatus.PENDING,
            )
            .with_for_update()
        )
        if renewal is None:
            raise BusinessRuleError("Bukti ini tidak ditemukan atau permintaan sudah selesai.")
        order = self._renewal_order(renewal.id)
        renewal.telegram_review_chat_id = None
        renewal.telegram_review_message_id = None
        self.db.commit()
        return order

    def complete_telegram_renewal(
        self,
        group_chat_id: int,
        message_id: int,
        telegram_admin_id: int,
    ) -> tuple[TelegramRenewalOrder, bool]:
        renewal = self.db.scalar(
            select(RentalRenewal)
            .where(
                RentalRenewal.telegram_review_chat_id == group_chat_id,
                RentalRenewal.telegram_review_message_id == message_id,
            )
            .with_for_update()
        )
        if renewal is None:
            raise BusinessRuleError("Balas foto bukti yang dikirim bot dengan /done.")
        order = self._renewal_order(renewal.id)
        if renewal.status == RenewalStatus.COMPLETED:
            return order, False
        if renewal.status not in (RenewalStatus.PENDING, RenewalStatus.APPROVED):
            raise BusinessRuleError("Permintaan perpanjangan ini tidak dapat diselesaikan.")
        rental = self.db.scalar(
            select(Rental).where(Rental.id == renewal.rental_id).with_for_update()
        )
        if (
            rental is None
            or rental.archived_at is not None
            or rental.status == RentalStatus.CANCELLED
        ):
            raise BusinessRuleError("Rental sudah dibatalkan atau diarsipkan.")
        if rental.expiration_date != renewal.previous_expiration_date:
            raise BusinessRuleError(
                "Tanggal rental berubah sejak permintaan dibuat. Minta admin meninjau ulang."
            )

        payment = self.db.scalar(
            select(Payment)
            .where(Payment.renewal_id == renewal.id)
            .order_by(Payment.created_at.desc())
            .limit(1)
            .with_for_update()
        )
        if payment is None:
            raise BusinessRuleError("Pembayaran untuk permintaan ini tidak ditemukan.")
        if payment.status == PaymentStatus.PENDING:
            now = utc_now()
            payment.status = PaymentStatus.PAID
            payment.paid_at = now
            payment.verified_at = now
        elif payment.status != PaymentStatus.PAID or payment.verified_at is None:
            raise BusinessRuleError("Pembayaran belum dapat diverifikasi.")
        if payment.amount != renewal.agreed_price or payment.currency != renewal.currency:
            raise BusinessRuleError("Nominal pembayaran tidak sesuai permintaan perpanjangan.")
        if renewal.status == RenewalStatus.PENDING:
            old_status = renewal.status
            renewal.status = RenewalStatus.APPROVED
            RenewalService(self.db)._audit(
                "renewal.approved",
                renewal,
                telegram_admin_id,
                old_status,
            )
        self.db.flush()
        RenewalService(self.db).complete_renewal(renewal.id, telegram_admin_id)
        return self._renewal_order(renewal.id), True

    def record_customer_consent(
        self,
        telegram_user_id: int,
        telegram_chat_id: int,
        *,
        granted: bool,
    ) -> bool:
        customer = self.db.scalar(
            select(Customer).where(
                Customer.telegram_user_id == telegram_user_id,
                Customer.telegram_chat_id == telegram_chat_id,
                Customer.archived_at.is_(None),
                Customer.status == CustomerStatus.ACTIVE,
            )
        )
        if customer is None:
            return False

        now = utc_now()
        for consent_type in (
            ConsentType.TELEGRAM_REMINDERS,
            ConsentType.TELEGRAM_RENEWAL_OFFERS,
        ):
            self.db.add(
                NotificationConsent(
                    customer_id=customer.id,
                    consent_type=consent_type,
                    consent_status=(ConsentStatus.GRANTED if granted else ConsentStatus.REVOKED),
                    source="telegram_bot",
                    consented_at=now if granted else None,
                    revoked_at=None if granted else now,
                )
            )
        self.db.commit()
        return True

    def create_store_feedback(
        self,
        telegram_user_id: int,
        telegram_chat_id: int,
        rating: int,
        message: str | None,
    ) -> tuple[uuid.UUID, str]:
        customer = self.db.scalar(
            select(Customer).where(
                Customer.telegram_user_id == telegram_user_id,
                Customer.telegram_chat_id == telegram_chat_id,
                Customer.archived_at.is_(None),
                Customer.status == CustomerStatus.ACTIVE,
            )
        )
        if customer is None:
            raise BusinessRuleError("Tautkan akun pelanggan terlebih dahulu melalui /start link_…")
        if not 1 <= rating <= 5:
            raise BusinessRuleError("Rating harus antara 1 dan 5.")

        feedback = StoreFeedback(
            customer_id=customer.id,
            customer_display_name=customer.display_name,
            rating=rating,
            message=message.strip() or None if message else None,
        )
        self.db.add(feedback)
        self.db.commit()
        self.db.refresh(feedback)
        return feedback.id, customer.display_name

    def respond_to_offer(
        self,
        offer_id: uuid.UUID,
        telegram_user_id: int,
        telegram_chat_id: int,
    ) -> str:
        customer = self.db.scalar(
            select(Customer).where(
                Customer.telegram_user_id == telegram_user_id,
                Customer.telegram_chat_id == telegram_chat_id,
                Customer.archived_at.is_(None),
                Customer.status == CustomerStatus.ACTIVE,
            )
        )
        if customer is None:
            raise BusinessRuleError("Akun Telegram pelanggan tidak terhubung.")

        offer = self.db.scalar(
            select(RenewalOffer).where(RenewalOffer.id == offer_id).with_for_update()
        )
        if offer is None or offer.customer_id != customer.id:
            raise BusinessRuleError("Penawaran tidak ditemukan untuk akun ini.")
        if offer.status == RenewalOfferStatus.SELECTED:
            return "Permintaan penawaran ini sudah tercatat sebelumnya."
        if offer.status != RenewalOfferStatus.ACTIVE:
            raise BusinessRuleError("Penawaran sudah tidak berlaku.")
        if offer.expires_at <= utc_now():
            offer.status = RenewalOfferStatus.EXPIRED
            self.db.commit()
            raise BusinessRuleError("Penawaran telah kedaluwarsa.")
        if not self._has_current_consent(
            customer.id,
            ConsentType.TELEGRAM_RENEWAL_OFFERS,
        ):
            raise BusinessRuleError("Persetujuan untuk penawaran Telegram tidak aktif.")

        rental = self.db.scalar(
            select(Rental)
            .where(
                Rental.id == offer.rental_id,
                Rental.customer_id == customer.id,
                Rental.archived_at.is_(None),
                Rental.status != RentalStatus.CANCELLED,
            )
            .with_for_update()
        )
        if rental is None:
            raise BusinessRuleError("Rental terkait sudah tidak tersedia.")

        try:
            new_start_date, new_expiration_date = calculate_renewal_dates(
                previous_expiration_date=rental.expiration_date,
                duration_value=offer.offered_duration_value,
                duration_unit=offer.offered_duration_unit,
                renewal_model=offer.renewal_model,
            )
        except ValueError:
            new_start_date = (
                current_wib_date()
                if offer.renewal_model == "IMMEDIATE"
                else rental.expiration_date + timedelta(days=1)
            )
            new_expiration_date = calculate_expiration_date(
                new_start_date,
                offer.offered_duration_value,
                offer.offered_duration_unit,
            )

        renewal = RentalRenewal(
            rental_id=rental.id,
            previous_start_date=rental.start_date,
            previous_expiration_date=rental.expiration_date,
            new_start_date=new_start_date,
            new_expiration_date=new_expiration_date,
            duration_value=offer.offered_duration_value,
            duration_unit=offer.offered_duration_unit,
            renewal_model=offer.renewal_model,
            agreed_price=offer.offered_price,
            currency=offer.currency,
            status=RenewalStatus.PENDING,
        )
        self.db.add(renewal)
        self.db.flush()
        offer.status = RenewalOfferStatus.SELECTED
        offer.selected_at = utc_now()
        response_text = (
            "✅ Permintaan perpanjangan sudah dicatat untuk ditinjau admin. "
            "Admin akan mengonfirmasi model/tanggal mulai. "
            "Rental belum aktif diperpanjang dan pembayaran belum diverifikasi."
        )

        self.db.add(
            NotificationResponse(
                rental_id=rental.id,
                customer_id=customer.id,
                renewal_offer_id=offer.id,
                response_type=CustomerResponseType.SELECT_OFFER,
                responded_at=utc_now(),
            )
        )
        self.db.commit()
        return response_text

    def decline_offer(
        self,
        offer_id: uuid.UUID,
        telegram_user_id: int,
        telegram_chat_id: int,
    ) -> str:
        customer = self.db.scalar(
            select(Customer).where(
                Customer.telegram_user_id == telegram_user_id,
                Customer.telegram_chat_id == telegram_chat_id,
                Customer.archived_at.is_(None),
                Customer.status == CustomerStatus.ACTIVE,
            )
        )
        if customer is None:
            raise BusinessRuleError("Akun Telegram pelanggan tidak terhubung.")
        offer = self.db.scalar(
            select(RenewalOffer).where(RenewalOffer.id == offer_id).with_for_update()
        )
        if offer is None or offer.customer_id != customer.id:
            raise BusinessRuleError("Penawaran tidak ditemukan untuk akun ini.")

        existing_response = self.db.scalar(
            select(NotificationResponse.id).where(
                NotificationResponse.renewal_offer_id == offer.id,
                NotificationResponse.customer_id == customer.id,
                NotificationResponse.response_type == CustomerResponseType.DECLINE_OFFER,
            )
        )
        if offer.status == RenewalOfferStatus.DECLINED and existing_response is not None:
            return "Respons Anda sudah tercatat sebelumnya."
        if offer.status != RenewalOfferStatus.ACTIVE:
            raise BusinessRuleError("Penawaran sudah tidak berlaku.")

        now = utc_now()
        if offer.expires_at <= now:
            offer.status = RenewalOfferStatus.EXPIRED
            self.db.commit()
            raise BusinessRuleError("Penawaran telah kedaluwarsa.")

        rental = self.db.scalar(
            select(Rental)
            .where(
                Rental.id == offer.rental_id,
                Rental.customer_id == customer.id,
                Rental.archived_at.is_(None),
                Rental.status != RentalStatus.CANCELLED,
            )
            .with_for_update()
        )
        if rental is None:
            raise BusinessRuleError("Rental terkait sudah tidak tersedia.")

        offer.status = RenewalOfferStatus.DECLINED
        self.db.add(
            NotificationResponse(
                rental_id=rental.id,
                customer_id=customer.id,
                renewal_offer_id=offer.id,
                response_type=CustomerResponseType.DECLINE_OFFER,
                responded_at=now,
            )
        )
        self.db.commit()
        return "🙏 Respons Anda sudah dicatat. Rental tidak berubah."

    def _has_current_consent(
        self,
        customer_id: uuid.UUID,
        consent_type: ConsentType,
    ) -> bool:
        consent = self.db.scalar(
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
