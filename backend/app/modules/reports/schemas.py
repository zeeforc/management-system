"""Pydantic schemas for dashboard metrics (Section 12.1)."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class DashboardSummaryRead(BaseModel):
    wib_reference_date: date
    total_products: int
    total_active_variants: int
    total_customers: int
    active_rentals: int
    rentals_expiring_in_5_days: int
    rentals_expiring_in_3_days: int
    rentals_expiring_tomorrow: int
    expired_rentals: int
    pending_renewal_requests: int
    pending_payment_verifications: int
    verified_payment_totals: Decimal
    currency: str = "IDR"
    failed_notifications: int
