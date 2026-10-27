"""Database-side aggregation service for dashboard metrics (Section 7 & 12.1)."""

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.customers.models import Customer
from app.modules.notifications.models import Notification
from app.modules.payments.models import Payment
from app.modules.products.models import Product, ProductVariant
from app.modules.renewals.models import RentalRenewal
from app.modules.rentals.models import Rental
from app.modules.reports.schemas import (
    DashboardOverviewRead,
    DashboardRentalPreviewRead,
    DashboardSummaryRead,
)
from app.shared.datetime_utils import (
    current_wib_date,
    days_until_expiration,
    derive_effective_rental_status,
)
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
        """Compute dashboard metrics in one database round trip."""
        today = current_wib_date()
        non_cancelled_rentals = (
            Rental.archived_at.is_(None),
            Rental.status != RentalStatus.CANCELLED,
        )

        def count(model_column, *criteria):
            return select(func.count(model_column)).where(*criteria).scalar_subquery()

        statement = select(
            count(Product.id, Product.archived_at.is_(None)).label("total_products"),
            count(
                ProductVariant.id,
                ProductVariant.archived_at.is_(None),
                ProductVariant.status == VariantStatus.ACTIVE,
            ).label("total_active_variants"),
            count(Customer.id, Customer.archived_at.is_(None)).label("total_customers"),
            count(
                Rental.id,
                *non_cancelled_rentals,
                Rental.start_date <= today,
                Rental.expiration_date >= today,
            ).label("active_rentals"),
            count(
                Rental.id,
                *non_cancelled_rentals,
                Rental.expiration_date == today + timedelta(days=5),
            ).label("rentals_expiring_in_5_days"),
            count(
                Rental.id,
                *non_cancelled_rentals,
                Rental.expiration_date == today + timedelta(days=3),
            ).label("rentals_expiring_in_3_days"),
            count(
                Rental.id,
                *non_cancelled_rentals,
                Rental.expiration_date == today + timedelta(days=1),
            ).label("rentals_expiring_tomorrow"),
            count(
                Rental.id,
                *non_cancelled_rentals,
                Rental.expiration_date < today,
            ).label("expired_rentals"),
            count(
                RentalRenewal.id,
                RentalRenewal.status == RenewalStatus.PENDING,
            ).label("pending_renewal_requests"),
            count(Payment.id, Payment.status == PaymentStatus.PENDING).label(
                "pending_payment_verifications"
            ),
            select(
                func.coalesce(func.sum(Payment.amount), Decimal("0.00"))
            )
            .where(
                Payment.status == PaymentStatus.PAID,
                Payment.verified_at.is_not(None),
            )
            .scalar_subquery()
            .label("verified_payment_totals"),
            count(
                Notification.id,
                Notification.status.in_(
                    (
                        NotificationStatus.FAILED_RETRYABLE,
                        NotificationStatus.FAILED_PERMANENT,
                        NotificationStatus.AMBIGUOUS,
                    )
                ),
            ).label("failed_notifications"),
        )
        row = self.db.execute(statement).one()

        return DashboardSummaryRead(
            wib_reference_date=today,
            total_products=int(row.total_products or 0),
            total_active_variants=int(row.total_active_variants or 0),
            total_customers=int(row.total_customers or 0),
            active_rentals=int(row.active_rentals or 0),
            rentals_expiring_in_5_days=int(row.rentals_expiring_in_5_days or 0),
            rentals_expiring_in_3_days=int(row.rentals_expiring_in_3_days or 0),
            rentals_expiring_tomorrow=int(row.rentals_expiring_tomorrow or 0),
            expired_rentals=int(row.expired_rentals or 0),
            pending_renewal_requests=int(row.pending_renewal_requests or 0),
            pending_payment_verifications=int(row.pending_payment_verifications or 0),
            verified_payment_totals=Decimal(str(row.verified_payment_totals or 0)),
            currency="IDR",
            failed_notifications=int(row.failed_notifications or 0),
        )

    def get_dashboard_overview(self) -> DashboardOverviewRead:
        today = current_wib_date()
        summary = self.get_dashboard_summary()
        rows = self.db.execute(
            select(Rental, Customer.display_name, Product.name, ProductVariant.name)
            .join(Customer, Customer.id == Rental.customer_id)
            .join(Product, Product.id == Rental.product_id)
            .join(ProductVariant, ProductVariant.id == Rental.product_variant_id)
            .where(
                Rental.archived_at.is_(None),
                Rental.status != RentalStatus.CANCELLED,
                Rental.status != RentalStatus.EXPIRED,
                Rental.expiration_date >= today,
            )
            .order_by(Rental.expiration_date.asc(), Rental.created_at.desc())
            .limit(3)
        ).all()
        previews = [
            DashboardRentalPreviewRead(
                id=rental.id,
                customer_name=customer_name,
                product_name=product_name,
                variant_name=variant_name,
                expiration_date=rental.expiration_date,
                effective_status=derive_effective_rental_status(
                    stored_status=rental.status,
                    start_date=rental.start_date,
                    expiration_date=rental.expiration_date,
                    wib_today=today,
                ),
                days_remaining=days_until_expiration(rental.expiration_date, wib_today=today),
            )
            for rental, customer_name, product_name, variant_name in rows
        ]
        return DashboardOverviewRead(summary=summary, upcoming_rentals=previews)
