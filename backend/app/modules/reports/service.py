"""Database-side aggregation service for dashboard metrics (Section 7 & 12.1)."""

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.customers.models import Customer
from app.modules.notifications.models import Notification
from app.modules.payments.models import Payment
from app.modules.products.models import Product, ProductVariant
from app.modules.rentals.models import Rental
from app.modules.renewals.models import RentalRenewal
from app.modules.reports.schemas import DashboardSummaryRead
from app.shared.datetime_utils import current_wib_date
from app.shared.enums import (
    NotificationStatus,
    PaymentStatus,
    RenewalStatus,
    RentalStatus,
    VariantStatus,
)


class ReportService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_dashboard_summary(self) -> DashboardSummaryRead:
        """Compute all 12 dashboard metrics using database-side aggregation."""
        today = current_wib_date()

        total_products = (
            self.db.scalar(
                select(func.count(Product.id)).where(Product.archived_at.is_(None))
            )
            or 0
        )
        total_active_variants = (
            self.db.scalar(
                select(func.count(ProductVariant.id)).where(
                    ProductVariant.archived_at.is_(None),
                    ProductVariant.status == VariantStatus.ACTIVE,
                )
            )
            or 0
        )
        total_customers = (
            self.db.scalar(
                select(func.count(Customer.id)).where(Customer.archived_at.is_(None))
            )
            or 0
        )

        non_cancelled_rentals = (
            Rental.archived_at.is_(None),
            Rental.status != RentalStatus.CANCELLED,
        )

        active_rentals = (
            self.db.scalar(
                select(func.count(Rental.id)).where(
                    *non_cancelled_rentals,
                    Rental.start_date <= today,
                    Rental.expiration_date >= today,
                )
            )
            or 0
        )
        rentals_expiring_in_5_days = (
            self.db.scalar(
                select(func.count(Rental.id)).where(
                    *non_cancelled_rentals,
                    Rental.expiration_date == today + timedelta(days=5),
                )
            )
            or 0
        )
        rentals_expiring_in_3_days = (
            self.db.scalar(
                select(func.count(Rental.id)).where(
                    *non_cancelled_rentals,
                    Rental.expiration_date == today + timedelta(days=3),
                )
            )
            or 0
        )
        rentals_expiring_tomorrow = (
            self.db.scalar(
                select(func.count(Rental.id)).where(
                    *non_cancelled_rentals,
                    Rental.expiration_date == today + timedelta(days=1),
                )
            )
            or 0
        )
        expired_rentals = (
            self.db.scalar(
                select(func.count(Rental.id)).where(
                    *non_cancelled_rentals,
                    Rental.expiration_date < today,
                )
            )
            or 0
        )

        pending_renewal_requests = (
            self.db.scalar(
                select(func.count(RentalRenewal.id)).where(
                    RentalRenewal.status == RenewalStatus.PENDING
                )
            )
            or 0
        )
        pending_payment_verifications = (
            self.db.scalar(
                select(func.count(Payment.id)).where(Payment.status == PaymentStatus.PENDING)
            )
            or 0
        )
        verified_payment_totals = self.db.scalar(
            select(func.coalesce(func.sum(Payment.amount), Decimal("0.00"))).where(
                Payment.status == PaymentStatus.PAID,
                Payment.verified_at.is_not(None),
            )
        ) or Decimal("0.00")

        failed_notifications = (
            self.db.scalar(
                select(func.count(Notification.id)).where(
                    Notification.status.in_(
                        [
                            NotificationStatus.FAILED_RETRYABLE,
                            NotificationStatus.FAILED_PERMANENT,
                            NotificationStatus.AMBIGUOUS,
                        ]
                    )
                )
            )
            or 0
        )

        return DashboardSummaryRead(
            wib_reference_date=today,
            total_products=int(total_products),
            total_active_variants=int(total_active_variants),
            total_customers=int(total_customers),
            active_rentals=int(active_rentals),
            rentals_expiring_in_5_days=int(rentals_expiring_in_5_days),
            rentals_expiring_in_3_days=int(rentals_expiring_in_3_days),
            rentals_expiring_tomorrow=int(rentals_expiring_tomorrow),
            expired_rentals=int(expired_rentals),
            pending_renewal_requests=int(pending_renewal_requests),
            pending_payment_verifications=int(pending_payment_verifications),
            verified_payment_totals=Decimal(str(verified_payment_totals)),
            currency="IDR",
            failed_notifications=int(failed_notifications),
        )
