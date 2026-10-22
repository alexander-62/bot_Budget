"""Append-only category management. Existing expense history stays untouched."""
from threading import Lock
from constants import CATEGORIES_SHEET_NAME
from services.google_sheets import get_spreadsheet, find_worksheet_case_insensitive, normalize_text
from services.budget import clear_budget_snapshot_cache, _is_active

_lock = Lock()
NAME_MAX_LENGTH = 64


def validate_name(raw: str) -> str:
    name = " ".join(raw.split())
    if not name or len(name) > NAME_MAX_LENGTH or any(ord(c) < 32 for c in raw):
        raise ValueError("Название должно содержать от 1 до 64 символов без переносов строк.")
    return name


def create_category(category: str, first_subcategory: str):
    return _append(category, first_subcategory, new_category=True)


def create_subcategory(category: str, subcategory: str):
    return _append(category, subcategory, new_category=False)


def _append(category, subcategory, *, new_category):
    category, subcategory = validate_name(category), validate_name(subcategory)
    with _lock:
        ws = find_worksheet_case_insensitive(get_spreadsheet(), CATEGORIES_SHEET_NAME)
        rows = ws.get_all_values()
        if not rows or [normalize_text(v) for v in rows[0][:3]] != ["категория", "подкатегория", "активно"]:
            raise ValueError("Лист «Категории»: проверьте заголовки первых трёх столбцов.")
        matching = [r for r in rows[1:] if r and normalize_text(r[0]) == normalize_text(category)]
        if new_category and matching:
            raise ValueError("Такая категория уже существует. Выберите добавление подкатегории.")
        if not new_category:
            active = [r for r in matching if len(r) > 2 and _is_active(r[2])]
            if not active:
                raise ValueError("Категория больше не активна. Откройте настройки заново.")
            category = active[0][0].strip()
        if any(len(r) > 1 and normalize_text(r[1]) == normalize_text(subcategory) for r in matching):
            raise ValueError("Такая подкатегория уже существует, в том числе среди неактивных.")
        order = 0
        for row in rows[1:]:
            try:
                order = max(order, int(row[3]))
            except (IndexError, ValueError):
                pass
        if len(rows[0]) < 4:
            ws.update(range_name="D1", values=[["Порядок"]], value_input_option="RAW")
        ws.append_row([category, subcategory, "TRUE", order + 1], value_input_option="RAW", table_range="A:D")
        clear_budget_snapshot_cache()
        return category, subcategory
