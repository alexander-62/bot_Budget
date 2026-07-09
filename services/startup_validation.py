from __future__ import annotations

from dataclasses import dataclass

from config import BOT_TOKEN, SPREADSHEET_ID, WEBAPP_HOST, WEBAPP_PORT, get_credentials_path
from constants import (
    CATEGORIES_SHEET_NAME,
    EXPENSES_SHEET_NAME,
    LIMITS_SHEET_NAME,
    SHOPPING_SHEET_NAME,
    USERS_SHEET_NAME,
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
    for rule in _WORKSHEET_RULES:
        worksheet = find_worksheet_case_insensitive(spreadsheet, rule.name)
        if not rule.required_headers:
            continue

        rows = worksheet.get_all_values()
        if not rows:
            raise StartupValidationError(f"Worksheet '{rule.name}' is empty.")

        header = tuple(normalize_text(value) for value in rows[0])
        for required in rule.required_headers:
            if required not in header:
                raise StartupValidationError(
                    f"Worksheet '{rule.name}' is missing required header '{required}'."
                )
