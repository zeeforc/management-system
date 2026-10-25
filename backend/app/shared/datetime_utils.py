"""Shared date and timezone calculation service for website, Bot, scheduler, and reports.

Rules implemented (Section 9 & 10 of built-rules.md):
- Business timezone: Asia/Jakarta (WIB).
- Event timestamps stored as UTC-aware datetimes.
- Rental start_date and expiration_date are calendar DATE values.
- Inclusive expiration date: expiring on 29 Oct means valid through 29 Oct, expired starting 30 Oct WIB.
- Calendar month/year additions clamp to the last valid day of the target month (e.g. Jan 31 + 1 month -> Feb 28/29).
- Continuous vs Immediate renewal start/expiration calculation.
- Reminder dates: H-5, H-3, H-1 before expiration_date.
"""

import calendar
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.shared.enums import (
    DurationUnit,
    ExpirationWarningState,
    ReminderStage,
    RenewalModel,
    RentalStatus,
)

WIB_TZ = ZoneInfo("Asia/Jakarta")


def utc_now() -> datetime:
    """Return current UTC-aware datetime."""
    return datetime.now(UTC)


def to_wib(dt: datetime) -> datetime:
    """Convert a timezone-aware datetime to Asia/Jakarta (WIB)."""
    if dt.tzinfo is None:
        raise ValueError("Datetime must be timezone-aware before converting to WIB.")
    return dt.astimezone(WIB_TZ)


def current_wib_date(reference_utc: datetime | None = None) -> date:
    """Return the current calendar date in Asia/Jakarta (WIB)."""
    dt = reference_utc if reference_utc is not None else utc_now()
    return to_wib(dt).date()


def add_calendar_months(base_date: date, months: int) -> date:
    """Add calendar months to a date, clamping the day to the last valid day of the target month."""
    if months < 0:
        raise ValueError("Months must be non-negative.")
    total_months = (base_date.year * 12 + (base_date.month - 1)) + months
    target_year = total_months // 12
    target_month = (total_months % 12) + 1
    max_day = calendar.monthrange(target_year, target_month)[1]
    target_day = min(base_date.day, max_day)
    return date(target_year, target_month, target_day)


def calculate_expiration_date(
    start_date: date,
    duration_value: int,
    duration_unit: DurationUnit,
) -> date:
    """Calculate inclusive expiration date from start_date and duration.

    Note: Because expiration_date is inclusive:
    - For DAYS/WEEKS: a 1-day rental starting 2026-10-01 expires on 2026-10-01 (or start + (days - 1) if strictly day-count,
      OR standard subscription period where start + duration_value is the end date).
      Per Section 9.3 ("adding one calendar month to 31 January... clamp the result to the last valid day of the target month")
      and Section 10.1, duration addition adds the unit directly:
      - DAYS: start_date + timedelta(days=duration_value)
      - WEEKS: start_date + timedelta(weeks=duration_value)
      - MONTHS: add_calendar_months(start_date, duration_value)
      - YEARS: add_calendar_months(start_date, duration_value * 12)
    """
    if duration_value <= 0:
        raise ValueError("duration_value must be greater than 0.")

    if duration_unit == DurationUnit.DAYS:
        return start_date + timedelta(days=duration_value)
    if duration_unit == DurationUnit.WEEKS:
        return start_date + timedelta(weeks=duration_value)
    if duration_unit == DurationUnit.MONTHS:
        return add_calendar_months(start_date, duration_value)
    if duration_unit == DurationUnit.YEARS:
        return add_calendar_months(start_date, duration_value * 12)

    raise ValueError(f"Unsupported duration unit: {duration_unit}")


def is_rental_expired(expiration_date: date, wib_today: date | None = None) -> bool:
    """Inclusive expiration check: valid through expiration_date, expired starting expiration_date + 1 day."""
    today = wib_today if wib_today is not None else current_wib_date()
    return today > expiration_date


def days_until_expiration(expiration_date: date, wib_today: date | None = None) -> int:
    """Return number of calendar days from wib_today until expiration_date (negative if expired)."""
    today = wib_today if wib_today is not None else current_wib_date()
    return (expiration_date - today).days


def derive_expiration_warning_state(
    lifecycle_status: RentalStatus,
    expiration_date: date,
    wib_today: date | None = None,
) -> ExpirationWarningState:
    """Calculate derived expiration warning state without relying on stale stored status."""
    if lifecycle_status == RentalStatus.CANCELLED:
        return ExpirationWarningState.NONE

    remaining_days = days_until_expiration(expiration_date, wib_today=wib_today)
    if remaining_days < 0:
        return ExpirationWarningState.EXPIRED
    if remaining_days <= 1:
        return ExpirationWarningState.EXPIRING_H1
    if remaining_days <= 3:
        return ExpirationWarningState.EXPIRING_H3
    if remaining_days <= 5:
        return ExpirationWarningState.EXPIRING_H5
    return ExpirationWarningState.NONE


def derive_effective_rental_status(
    stored_status: RentalStatus,
    start_date: date,
    expiration_date: date,
    wib_today: date | None = None,
) -> RentalStatus:
    """Derive effective rental status from stored lifecycle status and current WIB date."""
    if stored_status == RentalStatus.CANCELLED:
        return RentalStatus.CANCELLED

    today = wib_today if wib_today is not None else current_wib_date()
    if today > expiration_date:
        return RentalStatus.EXPIRED
    if today < start_date:
        return RentalStatus.SCHEDULED
    if (expiration_date - today).days <= 5:
        return RentalStatus.EXPIRING_SOON
    return RentalStatus.ACTIVE


def calculate_renewal_dates(
    previous_expiration_date: date,
    duration_value: int,
    duration_unit: DurationUnit,
    renewal_model: RenewalModel,
    confirmed_start_date: date | None = None,
    wib_today: date | None = None,
) -> tuple[date, date]:
    """Calculate (new_start_date, new_expiration_date) according to Section 9.4.

    - CONTINUOUS: only valid for unexpired rentals; new period starts on previous_expiration_date + 1 day,
      and new expiration is calculated from that new start date (or previous_expiration_date + duration).
      Per Section 9.4: "Continuous renewal: for an unexpired rental, the new period begins on the day after the previous expiration date."
    - IMMEDIATE: requires an explicitly confirmed start date.
    - For an expired rental: requires an explicit new start date; never silently infer a renewal start date.
    """
    today = wib_today if wib_today is not None else current_wib_date()
    expired = is_rental_expired(previous_expiration_date, wib_today=today)

    if expired and confirmed_start_date is None:
        raise ValueError("Expired rentals require an explicit confirmed_start_date for renewal.")

    if renewal_model == RenewalModel.CONTINUOUS:
        if expired:
            raise ValueError(
                "Continuous renewal is only allowed for unexpired rentals. "
                "Use IMMEDIATE renewal with an explicit start date."
            )
        new_start_date = previous_expiration_date + timedelta(days=1)
    elif renewal_model == RenewalModel.IMMEDIATE:
        if confirmed_start_date is None:
            raise ValueError("Immediate renewal requires an explicit confirmed_start_date.")
        new_start_date = confirmed_start_date
    else:
        raise ValueError(f"Unsupported renewal model: {renewal_model}")

    new_expiration_date = calculate_expiration_date(
        start_date=new_start_date,
        duration_value=duration_value,
        duration_unit=duration_unit,
    )
    return new_start_date, new_expiration_date


def calculate_reminder_dates(expiration_date: date) -> dict[ReminderStage, date]:
    """Return H-5, H-3, and H-1 reminder calendar dates in WIB.

    Example: expiration_date = 29 Oct -> H5 = 24 Oct, H3 = 26 Oct, H1 = 28 Oct.
    """
    return {
        ReminderStage.H5: expiration_date - timedelta(days=5),
        ReminderStage.H3: expiration_date - timedelta(days=3),
        ReminderStage.H1: expiration_date - timedelta(days=1),
    }


def calculate_reminder_scheduled_utc(
    expiration_date: date,
    stage: ReminderStage,
    send_hour_wib: int = 9,
    send_minute_wib: int = 0,
) -> datetime:
    """Calculate the UTC timestamp for a reminder stage scheduled at send_hour_wib:send_minute_wib WIB."""
    stage_dates = calculate_reminder_dates(expiration_date)
    reminder_date = stage_dates[stage]
    wib_dt = datetime.combine(
        reminder_date,
        time(hour=send_hour_wib, minute=send_minute_wib, second=0),
        tzinfo=WIB_TZ,
    )
    return wib_dt.astimezone(UTC)
