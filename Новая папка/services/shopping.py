from constants import SHOPPING_ITEM_MAX_LEN, SHOPPING_SHEET_NAME
from services.google_sheets import find_worksheet_case_insensitive, get_spreadsheet, normalize_text

_HEADER_TOKENS = {
    "список",
    "список покупок",
    "покупки",
    "продукты",
    "товары",
    "наименование",
    "позиция",
}


def _get_worksheet():
    spreadsheet = get_spreadsheet()
    return find_worksheet_case_insensitive(spreadsheet, SHOPPING_SHEET_NAME)


def _normalize_item(value: str) -> str:
    return normalize_text(value)


def _has_header(first_value: str) -> bool:
    return _normalize_item(first_value) in _HEADER_TOKENS


def get_shopping_entries() -> list[tuple[int, str]]:
    worksheet = _get_worksheet()
    values = worksheet.col_values(1)
    entries: list[tuple[int, str]] = []

    header_skipped = False
    for idx, raw in enumerate(values, start=1):
        item = raw.strip()
        if not item:
            continue
        if not header_skipped and idx == 1 and _has_header(item):
            header_skipped = True
            continue
        entries.append((idx, item))
    return entries


def get_shopping_items() -> list[str]:
    return [item for _, item in get_shopping_entries()]


def add_shopping_item(raw_item: str) -> tuple[bool, str]:
    item = " ".join(raw_item.strip().split())
    if not item:
        raise ValueError("Пустой ввод не допускается")
    if len(item) > SHOPPING_ITEM_MAX_LEN:
        raise ValueError(f"Максимальная длина позиции: {SHOPPING_ITEM_MAX_LEN} символов")

    entries = get_shopping_entries()
    normalized_new = _normalize_item(item)
    for _, existing in entries:
        if _normalize_item(existing) == normalized_new:
            return False, existing

    worksheet = _get_worksheet()
    values = worksheet.col_values(1)
    next_row = len(values) + 1 if values else 1
    worksheet.update(f"A{next_row}", [[item]], raw=False)
    return True, item


def remove_shopping_item_by_number(number: int) -> str:
    entries = get_shopping_entries()
    if number < 1 or number > len(entries):
        raise ValueError("Неверный номер, попробуйте снова")

    row_idx, item = entries[number - 1]
    worksheet = _get_worksheet()
    worksheet.delete_rows(row_idx)
    return item


def clear_shopping_list() -> None:
    worksheet = _get_worksheet()
    worksheet.batch_clear(["A:A"])

