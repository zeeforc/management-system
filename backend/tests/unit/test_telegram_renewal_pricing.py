import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.modules.telegram.handlers.renewals import _month_keyboard
from app.modules.telegram.service import TelegramService


@pytest.mark.parametrize(
    ("duration_value", "duration_unit", "default_price", "expected_monthly_price"),
    [
        (2, "MONTHS", "80000", "40000"),
        (1, "YEARS", "600000", "50000"),
        (2, "WEEKS", "14000", "30000"),
        (7, "DAYS", "7000", "30000"),
    ],
)
def test_variant_price_is_normalized_to_a_month(
    duration_value: int,
    duration_unit: str,
    default_price: str,
    expected_monthly_price: str,
) -> None:
    variant = SimpleNamespace(
        duration_value=duration_value,
        duration_unit=duration_unit,
        default_price=Decimal(default_price),
        currency="IDR",
    )

    assert TelegramService._variant_monthly_price(variant) == Decimal(expected_monthly_price)


def test_month_choices_show_total_price_for_each_duration() -> None:
    keyboard = _month_keyboard(uuid.uuid4(), Decimal("50000"))
    buttons = [button for row in keyboard.inline_keyboard for button in row]

    assert len(buttons) == 12
    assert buttons[0].text == "1 bulan · Rp 50.000"
    assert buttons[2].text == "3 bulan · Rp 150.000"
    assert buttons[-1].text == "12 bulan · Rp 600.000"
