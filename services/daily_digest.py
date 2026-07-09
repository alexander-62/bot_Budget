from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import logging
from zoneinfo import ZoneInfo

from constants import (
    DAILY_DIGEST_DISABLED_VALUES,
    DAILY_DIGEST_ENABLED_VALUES,
    DAILY_DIGEST_TIME,
    DAILY_DIGEST_TIMEZONE,
    EXPENSES_SHEET_NAME,
    USERS_SHEET_NAME,
)
from services.google_sheets import find_worksheet_case_insensitive, get_spreadsheet, normalize_text


@dataclass(frozen=True)
class DigestRecipient:
    username: str
    chat_id: int
    row_number: int
    last_digest_date: str


@dataclass(frozen=True)
class DailyDigestSummary:
    digest_date: date
    category_totals: tuple[tuple[str, Decimal], ...]

    @property
    def total(self) -> Decimal:
        return sum((amount for _, amount in self.category_totals), Decimal("0"))


def get_digest_recipients() -> list[DigestRecipient]:
    spreadsheet = get_spreadsheet()
    worksheet = find_worksheet_case_insensitive(spreadsheet, USERS_SHEET_NAME)
    rows = worksheet.get_all_values()
    if not rows:
        return []

    header = _header_index(rows[0])
    username_idx = _required_index(header, "username")
    chat_id_idx = _first_existing_index(header, ("user_id", "userid", "chat_id", "chatid", "id"))
    if chat_id_idx is None:
        return []

    digest_enabled_idx = header.get("digest_enabled")
    last_digest_date_idx = header.get("last_digest_date")

    recipients: list[DigestRecipient] = []
    for row_number, row in enumerate(rows[1:], start=2):
        username = _cell(row, username_idx).strip()
        if not username:
            continue

        chat_id_raw = _cell(row, chat_id_idx).strip()
        if not chat_id_raw:
            continue

        try:
            chat_id = int(chat_id_raw)
        except ValueError:
            logging.warning("Некорректный chat_id/user_id в листе Users: %r", chat_id_raw)
            continue

        enabled_raw = _cell(row, digest_enabled_idx).strip() if digest_enabled_idx is not None else ""
        if not _is_digest_enabled(enabled_raw):
            continue

        last_digest_date = _cell(row, last_digest_date_idx).strip() if last_digest_date_idx is not None else ""
        recipients.append(
            DigestRecipient(
                username=username,
                chat_id=chat_id,
                row_number=row_number,
                last_digest_date=last_digest_date,
            )
        )

    return recipients


def mark_digest_sent(row_number: int, digest_date: date) -> None:
    spreadsheet = get_spreadsheet()
    worksheet = find_worksheet_case_insensitive(spreadsheet, USERS_SHEET_NAME)
    rows = worksheet.get_all_values()
    if not rows:
        raise ValueError("Worksheet Users is empty.")

    header = _header_index(rows[0])
    last_digest_date_idx = header.get("last_digest_date")
    if last_digest_date_idx is None:
        raise ValueError("Worksheet Users is missing required header 'last_digest_date'.")

    worksheet.update_cell(row_number, last_digest_date_idx + 1, digest_date.isoformat())


def build_daily_digest_summary(digest_date: date) -> DailyDigestSummary:
    spreadsheet = get_spreadsheet()
    worksheet = find_worksheet_case_insensitive(spreadsheet, EXPENSES_SHEET_NAME)
    rows = worksheet.get_all_values()
    if not rows:
        return DailyDigestSummary(digest_date=digest_date, category_totals=tuple())

    header = _header_index(rows[0])
    date_idx = _required_index(header, "дата")
    category_idx = _required_index(header, "категория")
    amount_idx = _required_index(header, "сумма")

    totals: dict[str, Decimal] = {}
    for row in rows[1:]:
        if _parse_sheet_date(_cell(row, date_idx)) != digest_date:
            continue

        category = _cell(row, category_idx).strip() or "Без категории"
        amount = _parse_sheet_amount(_cell(row, amount_idx))
        if amount is None:
            continue

        totals[category] = totals.get(category, Decimal("0")) + amount

    category_totals = tuple(
        sorted(totals.items(), key=lambda item: (-item[1], normalize_text(item[0])))
    )
    return DailyDigestSummary(digest_date=digest_date, category_totals=category_totals)


def format_daily_digest_message(summary: DailyDigestSummary) -> str:
    if not summary.category_totals:
        return "\n".join(
            [
                "Добрый вечер.",
                "",
                "Сегодня пока не записали ни одной траты.",
                "",
                "Не забыли ли мы что-то записать?",
            ]
        )

    lines = ["Добрый вечер.", "", "Сегодня записали траты:", ""]
    for category, amount in summary.category_totals:
        lines.append(f"{category}: {_format_money(amount)}")
    lines.extend(["", f"Всего: {_format_money(summary.total)}", "", "Не забыли ли мы что-то еще записать?"])
    return "\n".join(lines)


def get_current_digest_date() -> date:
    return datetime.now(ZoneInfo(DAILY_DIGEST_TIMEZONE)).date()


def is_digest_due(now: datetime | None = None) -> bool:
    current = now or datetime.now(ZoneInfo(DAILY_DIGEST_TIMEZONE))
    if current.tzinfo is None:
        current = current.replace(tzinfo=ZoneInfo(DAILY_DIGEST_TIMEZONE))
    return current.timetz().replace(tzinfo=None) >= _parse_digest_time(DAILY_DIGEST_TIME)


def _header_index(header_row: list[str]) -> dict[str, int]:
    return {normalize_text(value): idx for idx, value in enumerate(header_row) if value.strip()}


def _required_index(header: dict[str, int], name: str) -> int:
    idx = header.get(name)
    if idx is None:
        raise ValueError(f"Required header '{name}' not found.")
    return idx


def _first_existing_index(header: dict[str, int], names: tuple[str, ...]) -> int | None:
    for name in names:
        idx = header.get(name)
        if idx is not None:
            return idx
    return None


def _cell(row: list[str], idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    return str(row[idx])


def _is_digest_enabled(raw_value: str) -> bool:
    normalized = normalize_text(raw_value)
    if not normalized:
        return True
    if normalized in DAILY_DIGEST_DISABLED_VALUES:
        return False
    if normalized in DAILY_DIGEST_ENABLED_VALUES:
        return True
    return True


def _parse_sheet_date(raw_value: str) -> date | None:
    value = raw_value.strip()
    if not value:
        return None

    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_sheet_amount(raw_value: str) -> Decimal | None:
    normalized = (
        raw_value.strip()
        .replace("\xa0", "")
        .replace(" ", "")
        .replace("€", "")
        .replace(",", ".")
    )
    if not normalized:
        return None

    try:
        return Decimal(normalized).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        logging.warning("Некорректная сумма в листе трат для дайджеста: %r", raw_value)
        return None


def _format_money(value: Decimal) -> str:
    rounded = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{int(rounded):,}".replace(",", " ") + " €"


def _parse_digest_time(value: str) -> time:
    hour_text, minute_text = value.split(":", 1)
    return time(hour=int(hour_text), minute=int(minute_text))
