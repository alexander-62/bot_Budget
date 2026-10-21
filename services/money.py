"""Currency-aware presentation shared by every budget view."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def currency_symbol(currency: str | None = None) -> str:
    if currency is None:
        from config import CURRENCY
        currency = CURRENCY
    return {"EUR": "€", "RUB": "₽"}[currency]


def parse_sheet_number(value: str) -> Decimal:
    normalized = str(value).replace("\xa0", "").replace(" ", "").replace("€", "").replace("₽", "").replace(",", ".")
    for code in ("EUR", "RUB", "руб.", "руб"):
        normalized = normalized.replace(code, "")
    try:
        number = Decimal(normalized)
        if not number.is_finite():
            raise InvalidOperation
        return number
    except InvalidOperation as exc:
        raise ValueError(f"Некорректное число: {value}") from exc


def format_number(value: str | Decimal) -> str:
    rounded = parse_sheet_number(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{int(rounded):,}".replace(",", " ")


def format_money(value: str | Decimal, currency: str | None = None) -> str:
    return f"{format_number(value)} {currency_symbol(currency)}"


def format_money_exact(value: str | Decimal, currency: str | None = None) -> str:
    amount = parse_sheet_number(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    rendered = f"{amount:,.2f}".replace(",", " ").replace(".", ",")
    return f"{rendered} {currency_symbol(currency)}"


def format_money_or_dash(value: str) -> str:
    return "—" if value.strip() in {"", "—", "не указан"} else format_money(value)


def format_remaining_with_alert(value: str) -> str:
    if value.strip() in {"", "—", "не указан"}:
        return "—"
    return format_money(value) + (" ⚠️" if parse_sheet_number(value) < 0 else "")
