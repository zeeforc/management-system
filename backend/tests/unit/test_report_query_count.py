from decimal import Decimal
from types import SimpleNamespace

from app.modules.reports.service import ReportService


class _SummaryResult:
    def one(self) -> SimpleNamespace:
        return SimpleNamespace(
            total_products=4,
            total_active_variants=9,
            total_customers=11,
            active_rentals=12,
            rentals_expiring_in_5_days=1,
            rentals_expiring_in_3_days=0,
            rentals_expiring_tomorrow=0,
            expired_rentals=0,
            pending_renewal_requests=0,
            pending_payment_verifications=0,
            verified_payment_totals=Decimal("0.00"),
            failed_notifications=0,
        )


class _CountingSession:
    def __init__(self) -> None:
        self.execute_calls = 0

    def execute(self, _statement) -> _SummaryResult:
        self.execute_calls += 1
        return _SummaryResult()


def test_dashboard_summary_uses_one_database_round_trip() -> None:
    db = _CountingSession()

    summary = ReportService(db).get_dashboard_summary()

    assert db.execute_calls == 1
    assert summary.total_products == 4
    assert summary.active_rentals == 12
