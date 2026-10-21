"""Optional per-budget active money sources, always read through Sheets adapter."""
from config import TRACK_MONEY_SOURCE
from constants import MONEY_SOURCES_SHEET_NAME
from services.google_sheets import get_spreadsheet, find_worksheet_case_insensitive, normalize_text


class MoneySourceError(ValueError):
    pass


def parse_money_sources(rows) -> list[str]:
    sources = []
    for row in rows[1:]:
        name = str(row[0]).strip() if row else ""
        active = normalize_text(str(row[1])) if len(row) > 1 else ""
        if not name or active not in {"true", "1", "yes", "y", "да"}:
            continue
        try:
            order = int(str(row[2]).strip()) if len(row) > 2 else 10**9
        except ValueError:
            order = 10**9
        sources.append((order, normalize_text(name), name))
    result, seen = [], set()
    for _, key, name in sorted(sources):
        if key not in seen:
            result.append(name)
            seen.add(key)
    return result


def get_money_sources() -> list[str]:
    if not TRACK_MONEY_SOURCE:
        return []
    worksheet = find_worksheet_case_insensitive(get_spreadsheet(), MONEY_SOURCES_SHEET_NAME)
    return parse_money_sources(worksheet.get_all_values())


def validate_money_source(source: str) -> str:
    if not source or source not in get_money_sources():
        raise MoneySourceError("Источник больше не доступен. Выберите активный источник заново.")
    return source
