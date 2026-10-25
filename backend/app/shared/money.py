"""Money utilities enforcing Decimal precision and currency consistency (IDR default)."""

from decimal import Decimal, ROUND_HALF_UP

SUPPORTED_CURRENCIES = {"IDR"}
DEFAULT_CURRENCY = "IDR"


def normalize_money(amount: Decimal | int | str, currency: str = DEFAULT_CURRENCY) -> Decimal:
    """Normalize a monetary value to a 2-decimal-place Decimal."""
    validate_currency(currency)
    if isinstance(amount, float):
        raise TypeError("Monetary amounts must not be passed as float; use Decimal, int, or str.")
    dec = Decimal(str(amount))
    if dec < Decimal("0"):
        raise ValueError("Monetary amount cannot be negative.")
    return dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def validate_currency(currency: str) -> str:
    """Validate that the currency code is supported."""
    normalized = currency.strip().upper()
    if normalized not in SUPPORTED_CURRENCIES:
        raise ValueError(f"Unsupported currency '{currency}'. Allowed: {sorted(SUPPORTED_CURRENCIES)}")
    return normalized


def format_idr(amount: Decimal | int | str) -> str:
    """Format an amount as Indonesian Rupiah (e.g., Rp 150.000)."""
    dec = normalize_money(amount, DEFAULT_CURRENCY)
    whole = int(dec.to_integral_value(rounding=ROUND_HALF_UP))
    formatted = f"{whole:,}".replace(",", ".")
    return f"Rp {formatted}"
