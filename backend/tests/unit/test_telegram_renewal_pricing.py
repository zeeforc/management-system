import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.modules.audit.models import AuditLog, SystemSetting
from app.modules.telegram.handlers.renewals import _month_keyboard
from app.modules.telegram.service import TelegramService


class FakeSettingsSession:
    def __init__(self) -> None:
        self.settings: dict[str, SystemSetting] = {}
        self.added: list[object] = []

    def get(self, model, key: str):
        return self.settings.get(key) if model is SystemSetting else None

    def add(self, value: object) -> None:
        self.added.append(value)
        if isinstance(value, SystemSetting):
            self.settings[value.key] = value

    def commit(self) -> None:
        pass


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


def test_admin_qris_update_persists_file_id_and_overrides_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "TELEGRAM_RENEWAL_QRIS_FILE_ID", "legacy-env-file-id")
    db = FakeSettingsSession()
    service = TelegramService(db)

    assert service.get_renewal_qris_file_id() == "legacy-env-file-id"

    service.set_renewal_qris_file_id("new-telegram-file-id", 987654321)

    assert service.get_renewal_qris_file_id() == "new-telegram-file-id"
    setting = db.settings["telegram_renewal_qris"]
    assert setting.value == {"file_id": "new-telegram-file-id"}
    audit = next(item for item in db.added if isinstance(item, AuditLog))
    assert audit.actor_id == "987654321"
    assert audit.after_data == {"configured": True}
