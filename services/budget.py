from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from constants import CATEGORIES_SHEET_NAME, EXPENSES_SHEET_NAME, LIMITS_SHEET_NAME
from services.google_sheets import (
    find_worksheet_case_insensitive,
    get_spreadsheet,
    normalize_text,
)

_TRUTHY_VALUES = {"true", "1", "yes", "y", "да"}


@dataclass(frozen=True)
class ActiveSubcategory:
    category: str
    subcategory: str
    sort_order: int


def get_current_month_key(today: date | None = None) -> str:
    current = today or date.today()
    return f"{current.year:04d}-{current.month:02d}"


def get_budget_limits() -> tuple[str, list[str]]:
    active_subcategories = _load_active_subcategories()
    categories = _unique_categories(active_subcategories)
    month_key = get_current_month_key()

    total_limit = _format_decimal(_sum_limits_for_month(active_subcategories, month_key))
    return total_limit, categories


def get_month_totals() -> tuple[str, str, str]:
    active_subcategories = _load_active_subcategories()
    month_key = get_current_month_key()
    limits_by_pair = _load_limits_for_month(month_key)
    spent_by_pair = _load_spent_for_month(month_key)

    total_limit = Decimal("0")
    total_spent = Decimal("0")
    for item in active_subcategories:
        key = (normalize_text(item.category), normalize_text(item.subcategory))
        total_limit += limits_by_pair.get(key, Decimal("0"))
        total_spent += spent_by_pair.get(key, Decimal("0"))

    total_remaining = total_limit - total_spent
    return (
        _format_decimal(total_limit),
        _format_decimal(total_spent),
        _format_decimal(total_remaining),
    )


def get_category_details(
    category_name: str,
) -> tuple[str, str, str, str, list[tuple[str, str, str, str]]]:
    active_subcategories = _load_active_subcategories()
    month_key = get_current_month_key()
    limits_by_pair = _load_limits_for_month(month_key)
    spent_by_pair = _load_spent_for_month(month_key)

    target_key = normalize_text(category_name)
    category_items = [item for item in active_subcategories if normalize_text(item.category) == target_key]
    if not category_items:
        raise ValueError("Категория не найдена")

    category_title = category_items[0].category
    subcategories: list[tuple[str, str, str, str]] = []
    category_limit = Decimal("0")
    category_spent = Decimal("0")

    for item in category_items:
        pair_key = (normalize_text(item.category), normalize_text(item.subcategory))
        sub_limit = limits_by_pair.get(pair_key, Decimal("0"))
        sub_spent = spent_by_pair.get(pair_key, Decimal("0"))
        sub_remaining = sub_limit - sub_spent

        category_limit += sub_limit
        category_spent += sub_spent
        subcategories.append(
            (
                item.subcategory,
                _format_decimal(sub_limit),
                _format_decimal(sub_spent),
                _format_decimal(sub_remaining),
            )
        )

    category_remaining = category_limit - category_spent
    return (
        category_title,
        _format_decimal(category_limit),
        _format_decimal(category_spent),
        _format_decimal(category_remaining),
        subcategories,
    )


def get_subcategories_for_category(category_name: str) -> list[str]:
    _, _, _, _, subcategories = get_category_details(category_name)
    return [name for name, *_ in subcategories]


def _load_active_subcategories() -> list[ActiveSubcategory]:
    spreadsheet = get_spreadsheet()
    worksheet = find_worksheet_case_insensitive(spreadsheet, CATEGORIES_SHEET_NAME)
    rows = worksheet.get_all_values()

    items: list[ActiveSubcategory] = []
    seen_pairs: set[tuple[str, str]] = set()
    for row in rows[1:]:
        category = row[0].strip() if len(row) > 0 else ""
        subcategory = row[1].strip() if len(row) > 1 else ""
        active_raw = row[2].strip() if len(row) > 2 else ""
        sort_order_raw = row[3].strip() if len(row) > 3 else ""

        if not category or not subcategory:
            continue
        if not _is_active(active_raw):
            continue

        key = (normalize_text(category), normalize_text(subcategory))
        if key in seen_pairs:
            continue
        seen_pairs.add(key)

        items.append(
            ActiveSubcategory(
                category=category,
                subcategory=subcategory,
                sort_order=_parse_sort_order(sort_order_raw),
            )
        )

    items.sort(key=lambda item: (item.sort_order, normalize_text(item.category), normalize_text(item.subcategory)))
    return items


def _load_limits_for_month(month_key: str) -> dict[tuple[str, str], Decimal]:
    spreadsheet = get_spreadsheet()
    worksheet = find_worksheet_case_insensitive(spreadsheet, LIMITS_SHEET_NAME)
    rows = worksheet.get_all_values()
    if not rows:
        return {}

    header = rows[0]
    month_col_idx = next(
        (idx for idx, value in enumerate(header) if value.strip() == month_key),
        None,
    )
    if month_col_idx is None:
        return {}

    limits: dict[tuple[str, str], Decimal] = {}
    for row in rows[1:]:
        category = row[0].strip() if len(row) > 0 else ""
        subcategory = row[1].strip() if len(row) > 1 else ""
        if not category or not subcategory:
            continue

        raw_limit = row[month_col_idx].strip() if len(row) > month_col_idx else ""
        limits[(normalize_text(category), normalize_text(subcategory))] = _parse_decimal(raw_limit)

    return limits


def _load_spent_for_month(month_key: str) -> dict[tuple[str, str], Decimal]:
    spreadsheet = get_spreadsheet()
    worksheet = find_worksheet_case_insensitive(spreadsheet, EXPENSES_SHEET_NAME)
    rows = worksheet.get_all_values()

    spent: dict[tuple[str, str], Decimal] = {}
    for row in rows[1:]:
        row_month_key = row[1].strip() if len(row) > 1 else ""
        category = row[3].strip() if len(row) > 3 else ""
        subcategory = row[4].strip() if len(row) > 4 else ""
        raw_amount = row[5].strip() if len(row) > 5 else ""

        if row_month_key != month_key or not category or not subcategory:
            continue

        key = (normalize_text(category), normalize_text(subcategory))
        spent[key] = spent.get(key, Decimal("0")) + _parse_decimal(raw_amount)

    return spent


def _sum_limits_for_month(active_subcategories: list[ActiveSubcategory], month_key: str) -> Decimal:
    limits_by_pair = _load_limits_for_month(month_key)
    total = Decimal("0")
    for item in active_subcategories:
        key = (normalize_text(item.category), normalize_text(item.subcategory))
        total += limits_by_pair.get(key, Decimal("0"))
    return total


def _unique_categories(active_subcategories: list[ActiveSubcategory]) -> list[str]:
    categories: OrderedDict[str, str] = OrderedDict()
    for item in active_subcategories:
        key = normalize_text(item.category)
        categories.setdefault(key, item.category)
    return list(categories.values())


def _is_active(value: str) -> bool:
    return normalize_text(value) in _TRUTHY_VALUES


def _parse_sort_order(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 10**9


def _parse_decimal(value: str) -> Decimal:
    normalized = value.strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    if not normalized:
        return Decimal("0")
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return Decimal("0")


def _format_decimal(value: Decimal) -> str:
    quantized = value.quantize(Decimal("0.01"))
    return format(quantized, "f").replace(".", ",")
