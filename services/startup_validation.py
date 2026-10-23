from __future__ import annotations

from dataclasses import dataclass

from config import BOT_TOKEN, SPREADSHEET_ID, WEBAPP_HOST, WEBAPP_PORT, PROFILE, get_credentials_path
from constants import (
    CATEGORIES_SHEET_NAME,
    EXPENSES_SHEET_NAME,
    LIMITS_SHEET_NAME,
    SHOPPING_SHEET_NAME,
    USERS_SHEET_NAME,
    MONEY_SOURCES_SHEET_NAME,
)
from services.google_sheets import find_worksheet_case_insensitive, get_spreadsheet, normalize_text


class StartupValidationError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorksheetRule:
    name: str
    required_headers: tuple[str, ...]


_WORKSHEET_RULES = (
    WorksheetRule(USERS_SHEET_NAME, ("username", "user_id", "digest_enabled", "last_digest_date")),
    WorksheetRule(CATEGORIES_SHEET_NAME, ("категория", "подкатегория", "активно")),
    WorksheetRule(LIMITS_SHEET_NAME, ("категория", "подкатегория")),
    WorksheetRule(EXPENSES_SHEET_NAME, ("дата", "месяц", "пользователь", "категория", "подкатегория", "сумма")),
    WorksheetRule(SHOPPING_SHEET_NAME, tuple()),
)


def get_worksheet_rules(profile, *, limits_enabled=True):
    rules = tuple(rule for rule in _WORKSHEET_RULES if limits_enabled or rule.name != LIMITS_SHEET_NAME)
    return rules + ((WorksheetRule(MONEY_SOURCES_SHEET_NAME, ("источник", "активно", "порядок")),) if profile.track_money_source else ())


def validate_startup() -> None:
    _validate_config()
    _validate_google_sheets_schema()


def _validate_config() -> None:
    if not BOT_TOKEN.strip():
        raise StartupValidationError("Config BOT_TOKEN is empty.")
    if not SPREADSHEET_ID.strip():
        raise StartupValidationError("Config SPREADSHEET_ID is empty.")
    if not WEBAPP_HOST.strip():
        raise StartupValidationError("Config WEBAPP_HOST is empty.")
    if not (1 <= WEBAPP_PORT <= 65535):
        raise StartupValidationError("Config WEBAPP_PORT must be between 1 and 65535.")

    credentials_path = get_credentials_path()
    if not credentials_path.exists():
        raise StartupValidationError("Configured GOOGLE_CREDENTIALS_FILE path does not exist.")
    if not credentials_path.is_file():
        raise StartupValidationError("Configured GOOGLE_CREDENTIALS_FILE path is not a file.")


def _validate_google_sheets_schema() -> None:
    spreadsheet = get_spreadsheet()
    from services.budget_settings import initialize_runtime_settings
    try:
        settings = initialize_runtime_settings()
    except ValueError as error:
        if str(error).startswith("Лист «Настройки»:"):
            raise StartupValidationError(str(error)) from None
        raise StartupValidationError("Не удалось загрузить лист «Настройки». Проверьте доступ и значения параметров.") from error
    except Exception as error:
        raise StartupValidationError("Не удалось загрузить лист «Настройки». Проверьте доступ и значения параметров.") from error
    for rule in get_worksheet_rules(PROFILE, limits_enabled=settings.monthly_limits_enabled):
        worksheet = find_worksheet_case_insensitive(spreadsheet, rule.name)
        if not rule.required_headers:
            continue

        rows = worksheet.get_all_values()
        if not rows:
            raise StartupValidationError(f"Worksheet '{rule.name}' is empty.")

        try:
            validate_worksheet_header(rule, rows[0], legacy=PROFILE.legacy, track_money_source=PROFILE.track_money_source)
            if rule.name == MONEY_SOURCES_SHEET_NAME:
                from services.money_sources import parse_money_sources
                if not parse_money_sources(rows):
                    raise ValueError("Лист «Источники»: добавьте хотя бы один активный источник.")
        except ValueError as error:
            raise StartupValidationError(str(error)) from None


def validate_worksheet_header(rule: WorksheetRule, values, *, legacy: bool, track_money_source: bool = False) -> None:
    """Position-based services require header order, not merely presence."""
    header = tuple(normalize_text(value) for value in values)
    expected = rule.required_headers
    if rule.name == EXPENSES_SHEET_NAME and (not legacy or track_money_source):
        expected += ("комментарий", "expense_id")
        if track_money_source:
            expected += ("источник",)
    for index, required in enumerate(expected):
        if required not in header:
            raise ValueError(f"Worksheet '{rule.name}' is missing required header '{required}'.")
        if index >= len(header) or header[index] != required:
            raise ValueError(f"Лист «{rule.name}»: столбец {index + 1} должен называться «{required}».")
