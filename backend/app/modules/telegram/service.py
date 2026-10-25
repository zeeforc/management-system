"""Telegram-facing workflows shared with the application's database services."""

import uuid
from datetime import timedelta
from html import escape

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError
from app.core.security import hash_token
from app.modules.customers.models import Customer, NotificationConsent, TelegramLinkToken
from app.modules.notifications.models import NotificationResponse
from app.modules.products.models import Product, ProductVariant
from app.modules.renewals.models import RenewalOffer, RentalRenewal
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
    RenewalOfferStatus,
    RenewalStatus,
    RentalStatus,
)
from app.shared.money import format_idr

PAGE_SIZE = 10


class TelegramService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.report_service = ReportService(db)

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
        stmt = select(Product).where(Product.archived_at.is_(None)).order_by(Product.name)
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
            variants = list(
                self.db.scalars(
                    select(ProductVariant)
                    .where(
                        ProductVariant.product_id == product.id,
                        ProductVariant.archived_at.is_(None),
                    )
                    .order_by(ProductVariant.name)
                ).all()
            )
            for variant in variants:
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

        conditions = [
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
        self.db.commit()
        return customer.display_name

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
