"""Unit tests for rental date, inclusive expiration, renewal models, reminder dates, and money rules (Section 9, 10, 15)."""

from datetime import date
from decimal import Decimal
import pytest

from app.shared.datetime_utils import (
    add_calendar_months,
    calculate_expiration_date,
    calculate_reminder_dates,
    calculate_renewal_dates,
    derive_effective_rental_status,
    derive_expiration_warning_state,
    is_rental_expired,
)
from app.shared.enums import (
    DurationUnit,
    ExpirationWarningState,
    ReminderStage,
    RenewalModel,
    RentalStatus,
)
from app.shared.money import format_idr, normalize_money


def test_inclusive_expiration_boundary() -> None:
    """Section 9.2: Rental expiring on 29 Oct is valid through 29 Oct and expired starting 30 Oct WIB."""
    exp = date(2026, 10, 29)
    assert is_rental_expired(exp, wib_today=date(2026, 10, 28)) is False
    assert is_rental_expired(exp, wib_today=date(2026, 10, 29)) is False
    assert is_rental_expired(exp, wib_today=date(2026, 10, 30)) is True


def test_calendar_month_addition_clamping() -> None:
    """Section 9.3: Adding 1 calendar month to 31 January clamps to the last valid day of February."""
    assert add_calendar_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_calendar_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert calculate_expiration_date(date(2026, 1, 31), 1, DurationUnit.MONTHS) == date(2026, 2, 28)


def test_reminder_date_calculations() -> None:
    """Section 10.1: Rental expiring on 29 October has reminder dates of 24 Oct (H-5), 26 Oct (H-3), 28 Oct (H-1)."""
    reminders = calculate_reminder_dates(date(2026, 10, 29))
    assert reminders[ReminderStage.H5] == date(2026, 10, 24)
    assert reminders[ReminderStage.H3] == date(2026, 10, 26)
    assert reminders[ReminderStage.H1] == date(2026, 10, 28)


def test_continuous_renewal_for_unexpired_rental() -> None:
    """Section 9.4: Continuous renewal starts on the day after previous_expiration_date."""
    new_start, new_exp = calculate_renewal_dates(
        previous_expiration_date=date(2026, 10, 29),
        duration_value=1,
        duration_unit=DurationUnit.MONTHS,
        renewal_model=RenewalModel.CONTINUOUS,
        wib_today=date(2026, 10, 26),
    )
    assert new_start == date(2026, 10, 30)
    assert new_exp == date(2026, 11, 30)


def test_expired_rental_requires_explicit_start_date() -> None:
    """Section 9.4: For an expired rental, require an explicit new start date; never silently infer."""
    with pytest.raises(ValueError, match="explicit confirmed_start_date"):
        calculate_renewal_dates(
            previous_expiration_date=date(2026, 10, 20),
            duration_value=1,
            duration_unit=DurationUnit.MONTHS,
            renewal_model=RenewalModel.IMMEDIATE,
            confirmed_start_date=None,
            wib_today=date(2026, 10, 24),
        )

    new_start, new_exp = calculate_renewal_dates(
        previous_expiration_date=date(2026, 10, 20),
        duration_value=30,
        duration_unit=DurationUnit.DAYS,
        renewal_model=RenewalModel.IMMEDIATE,
        confirmed_start_date=date(2026, 10, 24),
        wib_today=date(2026, 10, 24),
    )
    assert new_start == date(2026, 10, 24)
    assert new_exp == date(2026, 11, 23)


def test_derived_warning_and_effective_status() -> None:
    """Section 9.5: Derived warning state and effective rental status calculation."""
    exp = date(2026, 10, 29)
    assert (
        derive_expiration_warning_state(RentalStatus.ACTIVE, exp, wib_today=date(2026, 10, 24))
        == ExpirationWarningState.EXPIRING_H5
    )
    assert (
        derive_expiration_warning_state(RentalStatus.ACTIVE, exp, wib_today=date(2026, 10, 26))
        == ExpirationWarningState.EXPIRING_H3
    )
    assert (
        derive_expiration_warning_state(RentalStatus.ACTIVE, exp, wib_today=date(2026, 10, 28))
        == ExpirationWarningState.EXPIRING_H1
    )
    assert (
        derive_effective_rental_status(
            RentalStatus.ACTIVE,
            start_date=date(2026, 10, 1),
            expiration_date=exp,
            wib_today=date(2026, 10, 30),
        )
        == RentalStatus.EXPIRED
    )


def test_money_rejects_float_and_formats_idr() -> None:
    """Section 5: Never allow floating-point money; format IDR cleanly."""
    with pytest.raises(TypeError):
        normalize_money(150000.0)  # type: ignore[arg-type]

    assert normalize_money("150000") == Decimal("150000.00")
    assert format_idr(Decimal("150000.00")) == "Rp 150.000"
