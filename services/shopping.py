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
    added_items, existing_items = add_shopping_items([raw_item])
    if added_items:
        return True, added_items[0]
    return False, existing_items[0]


def add_shopping_items(raw_items: list[str]) -> tuple[list[str], list[str]]:
    if not raw_items:
        return [], []

    prepared_items: list[str] = []
    for raw_item in raw_items:
        item = " ".join(raw_item.strip().split())
        if not item:
            raise ValueError("Пустой ввод не допускается")
        if len(item) > SHOPPING_ITEM_MAX_LEN:
            raise ValueError(f"Максимальная длина позиции: {SHOPPING_ITEM_MAX_LEN} символов")
        prepared_items.append(item)

    entries = get_shopping_entries()
    existing_by_normalized: dict[str, str] = {}
    for _, existing in entries:
        normalized_existing = _normalize_item(existing)
        existing_by_normalized.setdefault(normalized_existing, existing)

    new_items: list[str] = []
    existing_items: list[str] = []
    first_new_by_normalized: dict[str, str] = {}
    seen_new_normalized: set[str] = set()

    for item in prepared_items:
        normalized_item = _normalize_item(item)
        existing_item = existing_by_normalized.get(normalized_item)
        if existing_item is not None:
            existing_items.append(existing_item)
            continue

        if normalized_item in seen_new_normalized:
            existing_items.append(first_new_by_normalized[normalized_item])
            continue

        seen_new_normalized.add(normalized_item)
        first_new_by_normalized[normalized_item] = item
        new_items.append(item)

    if new_items:
        worksheet = _get_worksheet()
        worksheet.append_rows([[item] for item in new_items], value_input_option="RAW")

    return new_items, existing_items


def add_shopping_item(raw_item: str) -> tuple[bool, str]:
    item = " ".join(raw_item.strip().split())
    if not item:
        raise ValueError("Пустой ввод не допускается")
    if len(item) > SHOPPING_ITEM_MAX_LEN:
        raise ValueError(f"Максимальная длина позиции: {SHOPPING_ITEM_MAX_LEN} символов")
    added_items, existing_items = add_shopping_items([item])
    if added_items:
        return True, added_items[0]
    return False, existing_items[0]


def remove_shopping_item_by_number(number: int) -> str:
    entries = get_shopping_entries()
    if number < 1 or number > len(entries):
        raise ValueError("Неверный номер, попробуйте снова")

    row_idx, item = entries[number - 1]
    worksheet = _get_worksheet()
    worksheet.delete_rows(row_idx)
    return item


def remove_shopping_items_by_numbers(numbers: list[int]) -> list[str]:
    if not numbers:
        raise ValueError("Неверный номер, попробуйте снова")

    entries = get_shopping_entries()
    if not entries:
        raise ValueError("Список пуст, удалять нечего")

    unique_numbers: list[int] = []
    seen: set[int] = set()
    for number in numbers:
        if number in seen:
            continue
        seen.add(number)
        unique_numbers.append(number)

    for number in unique_numbers:
        if number < 1 or number > len(entries):
            raise ValueError("Неверный номер, попробуйте снова")

    to_delete = [(entries[number - 1][0], entries[number - 1][1]) for number in unique_numbers]
    worksheet = _get_worksheet()
    for row_idx, _ in sorted(to_delete, key=lambda item: item[0], reverse=True):
        worksheet.delete_rows(row_idx)

    return [item for _, item in to_delete]


def clear_shopping_list() -> None:
    worksheet = _get_worksheet()
    worksheet.batch_clear(["A:A"])
