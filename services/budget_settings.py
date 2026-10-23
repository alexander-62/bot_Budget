"""Budget-owned settings in Sheets; local currency is a migration seed only.

All I/O functions are synchronous and must run through run_blocking in async code.
Presentation uses the in-memory snapshot and never performs network I/O.
"""
from dataclasses import dataclass
from threading import RLock
from time import monotonic

from services.google_sheets import get_spreadsheet, normalize_text

SETTINGS_SHEET = "Настройки"
HEADER = ["Параметр", "Значение"]
TTL_SECONDS = 5.0
_lock = RLock()


@dataclass(frozen=True)
class BudgetSettings:
    currency: str = "EUR"
    monthly_limits_enabled: bool = True


_runtime: BudgetSettings | None = None
_loaded_at = 0.0


def cached_settings() -> BudgetSettings:
    if _runtime is not None:
        return _runtime
    from config import CURRENCY
    return BudgetSettings(currency=CURRENCY)


def settings_initialized() -> bool:
    return _runtime is not None


def _worksheet(spreadsheet):
    for ws in spreadsheet.worksheets():
        if normalize_text(ws.title) == normalize_text(SETTINGS_SHEET):
            return ws
    return None


def _rows(ws):
    rows = ws.get_all_values()
    # Real Sheets returns [[]] for a newly created/cleared sheet. Fakes often
    # return []; both represent an empty sheet eligible for initialization.
    if not any(any(str(value).strip() for value in row) for row in rows):
        return [], {}
    if rows and [normalize_text(v) for v in rows[0][:2]] != [normalize_text(v) for v in HEADER]:
        raise ValueError("Лист «Настройки»: ожидаются столбцы «Параметр», «Значение».")
    indexed = {}
    for number, row in enumerate(rows[1:], 2):
        if not row or not str(row[0]).strip():
            continue
        key = normalize_text(str(row[0]))
        if key in indexed:
            raise ValueError(f"Лист «Настройки»: повтор параметра {key}.")
        indexed[key] = (number, str(row[1]).strip() if len(row) > 1 else "")
    return rows, indexed


def _parse(indexed):
    try:
        currency = indexed["currency"][1].upper()
        enabled = indexed["monthly_limits_enabled"][1].upper()
    except KeyError:
        raise ValueError("Лист «Настройки»: отсутствует currency или monthly_limits_enabled.") from None
    if currency not in {"EUR", "RUB"}:
        raise ValueError("Лист «Настройки»: currency должен быть EUR или RUB.")
    if enabled not in {"TRUE", "FALSE"}:
        raise ValueError("Лист «Настройки»: monthly_limits_enabled должен быть TRUE или FALSE.")
    return BudgetSettings(currency, enabled == "TRUE")


def read_settings(spreadsheet) -> BudgetSettings:
    ws = _worksheet(spreadsheet)
    if ws is None:
        raise ValueError("Не найден лист «Настройки». Запустите бота для первичного переноса настроек.")
    return _parse(_rows(ws)[1])


def ensure_settings(spreadsheet, initial_currency: str) -> BudgetSettings:
    """Initialize missing keys only. Existing invalid values fail visibly."""
    if initial_currency not in {"EUR", "RUB"}:
        raise ValueError("Неподдерживаемая исходная валюта.")
    with _lock:
        ws = _worksheet(spreadsheet)
        if ws is None:
            try:
                ws = spreadsheet.add_worksheet(title=SETTINGS_SHEET, rows=30, cols=2)
            except Exception:
                # Another worker may have created the sheet. Never hide other errors.
                ws = _worksheet(spreadsheet)
                if ws is None:
                    raise
        rows, indexed = _rows(ws)
        if not rows:
            ws.update(range_name="A1:B1", values=[HEADER], value_input_option="RAW")
        defaults = {"currency": initial_currency, "monthly_limits_enabled": "TRUE"}
        missing = [[key, value] for key, value in defaults.items() if key not in indexed]
        # Validate existing values before writing any missing defaults.
        _parse({**{key: (0, value) for key, value in defaults.items()}, **indexed})
        if missing:
            ws.append_rows(missing, value_input_option="RAW", table_range="A:B")
        return read_settings(spreadsheet)


def update_setting(spreadsheet, key: str, value: str, *, expected: str | None = None) -> BudgetSettings:
    if key not in {"currency", "monthly_limits_enabled"}:
        raise ValueError("Неизвестная настройка.")
    with _lock:
        ws = _worksheet(spreadsheet)
        if ws is None:
            raise ValueError("Не найден лист «Настройки».")
        _, indexed = _rows(ws)
        _parse(indexed)
        row, old_value = indexed[key]
        if expected is not None and old_value.upper() != expected.upper():
            raise ValueError("Настройка уже изменилась. Откройте настройки заново.")
        candidate = {**indexed, key: (row, value)}
        _parse(candidate)
        ws.update(range_name=f"B{row}", values=[[value]], value_input_option="RAW")
        return read_settings(spreadsheet)


def _publish(settings):
    global _runtime, _loaded_at
    changed = _runtime != settings
    _runtime, _loaded_at = settings, monotonic()
    if changed:
        from services.budget import clear_budget_snapshot_cache
        clear_budget_snapshot_cache()
    return settings


def initialize_runtime_settings():
    from config import CURRENCY
    with _lock:
        return _publish(ensure_settings(get_spreadsheet(), CURRENCY))


def refresh_runtime_settings(*, force=False):
    with _lock:
        if not force and _runtime is not None and monotonic() - _loaded_at < TTL_SECONDS:
            return _runtime
        return _publish(read_settings(get_spreadsheet()))


def set_runtime_setting(key, value, *, expected=None):
    with _lock:
        return _publish(update_setting(get_spreadsheet(), key, value, expected=expected))


def validate_limits_sheet():
    from constants import LIMITS_SHEET_NAME
    from services.google_sheets import find_worksheet_case_insensitive
    from services.startup_validation import WorksheetRule, validate_worksheet_header
    ws = find_worksheet_case_insensitive(get_spreadsheet(), LIMITS_SHEET_NAME)
    validate_worksheet_header(WorksheetRule(LIMITS_SHEET_NAME, ("категория", "подкатегория")), ws.row_values(1), legacy=True)
