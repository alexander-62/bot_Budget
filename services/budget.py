from constants import (
    BUDGET_SHEET_NAME,
    TOTAL_LIMIT_MARKER,
    TOTAL_REMAINING_MARKER,
    TOTAL_SPENT_MARKER,
)
from services.google_sheets import (
    find_worksheet_case_insensitive,
    get_spreadsheet,
    normalize_text,
)


def get_budget_limits() -> tuple[str, list[str]]:
    spreadsheet = get_spreadsheet()
    worksheet = find_worksheet_case_insensitive(spreadsheet, BUDGET_SHEET_NAME)

    all_rows = worksheet.get_all_values()
    categories: list[str] = []
    seen_categories: set[str] = set()

    for row in all_rows[1:]:
        name = row[0].strip() if len(row) > 0 else ""
        if not name:
            continue
        key = normalize_text(name)
        if key in seen_categories:
            continue
        seen_categories.add(key)
        categories.append(name)

    total_limit = _find_marker_value(
        all_rows=all_rows,
        marker_text=TOTAL_LIMIT_MARKER,
        marker_col_idx=8,  # I
        value_col_idx=9,  # J
    )

    if not total_limit:
        raise ValueError("Не найден общий лимит месяца в таблице")

    return total_limit, categories


def get_month_totals() -> tuple[str, str, str]:
    spreadsheet = get_spreadsheet()
    worksheet = find_worksheet_case_insensitive(spreadsheet, BUDGET_SHEET_NAME)
    all_rows = worksheet.get_all_values()

    total_limit = _find_marker_value(
        all_rows=all_rows,
        marker_text=TOTAL_LIMIT_MARKER,
        marker_col_idx=8,  # I
        value_col_idx=9,  # J
    )
    total_spent = _find_marker_value(
        all_rows=all_rows,
        marker_text=TOTAL_SPENT_MARKER,
        marker_col_idx=10,  # K
        value_col_idx=11,  # L
    )
    total_remaining = _find_marker_value(
        all_rows=all_rows,
        marker_text=TOTAL_REMAINING_MARKER,
        marker_col_idx=12,  # M
        value_col_idx=13,  # N
    )

    if not total_limit:
        raise ValueError("Не найден общий лимит месяца в таблице")
    if not total_spent:
        raise ValueError("Не найден итог потрачено за месяц в таблице")
    if not total_remaining:
        raise ValueError("Не найден итог осталось за месяц в таблице")

    return total_limit, total_spent, total_remaining


def get_category_details(
    category_name: str,
) -> tuple[str, str, str, str, list[tuple[str, str, str, str]]]:
    spreadsheet = get_spreadsheet()
    worksheet = find_worksheet_case_insensitive(spreadsheet, BUDGET_SHEET_NAME)
    all_rows = worksheet.get_all_values()

    target_key = normalize_text(category_name)
    start_idx = None

    for idx, row in enumerate(all_rows[1:], start=1):
        category_cell = row[0].strip() if len(row) > 0 else ""
        if normalize_text(category_cell) == target_key:
            start_idx = idx
            break

    if start_idx is None:
        raise ValueError("Категория не найдена")

    category_row = all_rows[start_idx]
    category_title = category_row[0].strip() if len(category_row) > 0 else category_name
    category_limit = category_row[3].strip() if len(category_row) > 3 else ""
    category_spent = category_row[5].strip() if len(category_row) > 5 else ""
    category_remaining = category_row[7].strip() if len(category_row) > 7 else ""
    if not category_limit:
        category_limit = "не указан"
    if not category_spent:
        category_spent = "—"
    if not category_remaining:
        category_remaining = "—"

    subcategories: list[tuple[str, str, str, str]] = []
    for row in all_rows[start_idx + 1 :]:
        next_category = row[0].strip() if len(row) > 0 else ""
        if next_category:
            break

        subcategory_name = row[1].strip() if len(row) > 1 else ""
        subcategory_limit = row[2].strip() if len(row) > 2 else ""
        subcategory_spent = row[4].strip() if len(row) > 4 else ""
        subcategory_remaining = row[6].strip() if len(row) > 6 else ""

        if not subcategory_name:
            continue
        if not subcategory_limit:
            subcategory_limit = "не указан"
        if not subcategory_spent:
            subcategory_spent = "—"
        if not subcategory_remaining:
            subcategory_remaining = "—"

        subcategories.append(
            (subcategory_name, subcategory_limit, subcategory_spent, subcategory_remaining)
        )

    return category_title, category_limit, category_spent, category_remaining, subcategories


def get_subcategories_for_category(category_name: str) -> list[str]:
    _, _, _, _, subcategories = get_category_details(category_name)
    return [name for name, *_ in subcategories]


def _find_marker_value(
    all_rows: list[list[str]], marker_text: str, marker_col_idx: int, value_col_idx: int
) -> str:
    for row in all_rows:
        marker = row[marker_col_idx] if len(row) > marker_col_idx else ""
        if normalize_text(marker) == marker_text:
            return row[value_col_idx].strip() if len(row) > value_col_idx else ""
    return ""
