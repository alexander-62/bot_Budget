from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from uuid import uuid4

import gspread

from constants import EXPENSES_SHEET_NAME
from services.budget import clear_budget_snapshot_cache, get_current_month_key
from services.google_sheets import find_worksheet_case_insensitive, get_spreadsheet


@dataclass(frozen=True)
class SavedExpense:
    expense_id: str
    sheet_name: str
    row_number: int
    row_range: str
    date: str
    month_key: str
    username: str
    category: str
    subcategory: str
    amount: str
    comment: str


class StaleExpenseError(ValueError):
    pass


def parse_amount(raw_amount: str) -> str:
    normalized = raw_amount.strip().replace(" ", "").replace(",", ".")
    if not normalized:
        raise ValueError("Пустая сумма")

    try:
        amount = Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError("Сумма должна быть числом") from exc

    if amount <= 0:
        raise ValueError("Сумма должна быть больше 0")

    rounded = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{rounded:.2f}".replace(".", ",")


def parse_amount_with_optional_comment(raw_input: str) -> tuple[str, str]:
    raw_text = raw_input.strip()
    if not raw_text:
        raise ValueError("Пустая сумма")

    try:
        return parse_amount(raw_text), ""
    except ValueError as full_parse_error:
        tokens = raw_text.split()
        for split_idx in range(len(tokens) - 1, 0, -1):
            amount_candidate = " ".join(tokens[:split_idx])
            comment_candidate = " ".join(tokens[split_idx:]).strip()
            if not comment_candidate:
                continue
            try:
                return parse_amount(amount_candidate), comment_candidate
            except ValueError:
                continue

        raise full_parse_error


_APPENDED_RANGE_RE = re.compile(r"(?:(?:'[^']+'|[^!]+)!)?([A-Z]+)(\d+):([A-Z]+)(\d+)$")


def _extract_row_number_from_append_response(
    response: object,
    worksheet_title: str,
    fallback_row_number: int,
) -> tuple[int, str]:
    updated_range = ""
    if isinstance(response, dict):
        updates = response.get("updates")
        if isinstance(updates, dict):
            updated_range = str(updates.get("updatedRange", "") or "")
        if not updated_range:
            updated_range = str(response.get("updatedRange", "") or "")
    else:
        updates = getattr(response, "updates", None)
        if updates is not None:
            updated_range = str(getattr(updates, "updatedRange", "") or "")
        if not updated_range:
            updated_range = str(getattr(response, "updatedRange", "") or "")

    if updated_range:
        range_tail = updated_range
        if "!" in range_tail:
            _, range_tail = range_tail.rsplit("!", 1)
        match = _APPENDED_RANGE_RE.match(range_tail)
        if match:
            return int(match.group(2)), updated_range

    row_range = f"{worksheet_title}!A{fallback_row_number}:H{fallback_row_number}"
    return fallback_row_number, row_range


def write_expense(
    username: str,
    category: str,
    subcategory: str,
    amount: str,
    comment: str = "",
) -> SavedExpense:
    spreadsheet = get_spreadsheet()
    worksheet = find_worksheet_case_insensitive(spreadsheet, EXPENSES_SHEET_NAME)
    today = datetime.now().strftime("%Y-%m-%d")
    month_key = get_current_month_key()
    numeric_amount = float(amount.replace(" ", "").replace(",", "."))
    expense_id = uuid4().hex

    response = worksheet.append_row(
        [
            today,
            month_key,
            username,
            category,
            subcategory,
            numeric_amount,
            comment,
            expense_id,
        ],
        value_input_option="RAW",
        insert_data_option="INSERT_ROWS",
        table_range="A:H",
    )
    fallback_row_number = len(worksheet.col_values(1))
    row_number, row_range = _extract_row_number_from_append_response(
        response=response,
        worksheet_title=worksheet.title,
        fallback_row_number=fallback_row_number,
    )
    clear_budget_snapshot_cache()

    return SavedExpense(
        expense_id=expense_id,
        sheet_name=worksheet.title,
        row_number=row_number,
        row_range=row_range,
        date=today,
        month_key=month_key,
        username=username,
        category=category,
        subcategory=subcategory,
        amount=amount,
        comment=comment,
    )


def update_expense(saved_expense: SavedExpense, amount: str, comment: str = "") -> SavedExpense:
    worksheet = _get_expenses_worksheet()
    current_row = _get_expense_row_values(worksheet, saved_expense.row_number)
    _assert_same_saved_expense(saved_expense, current_row)

    numeric_amount = float(amount.replace(" ", "").replace(",", "."))
    worksheet.update(
        range_name=f"A{saved_expense.row_number}:H{saved_expense.row_number}",
        values=[
            [
                saved_expense.date,
                saved_expense.month_key,
                saved_expense.username,
                saved_expense.category,
                saved_expense.subcategory,
                numeric_amount,
                comment,
                saved_expense.expense_id,
            ]
        ],
        raw=False,
    )
    clear_budget_snapshot_cache()

    return SavedExpense(
        expense_id=saved_expense.expense_id,
        sheet_name=worksheet.title,
        row_number=saved_expense.row_number,
        row_range=f"{worksheet.title}!A{saved_expense.row_number}:H{saved_expense.row_number}",
        date=saved_expense.date,
        month_key=saved_expense.month_key,
        username=saved_expense.username,
        category=saved_expense.category,
        subcategory=saved_expense.subcategory,
        amount=amount,
        comment=comment,
    )


def delete_expense(saved_expense: SavedExpense) -> None:
    worksheet = _get_expenses_worksheet()
    current_row = _get_expense_row_values(worksheet, saved_expense.row_number)
    _assert_same_saved_expense(saved_expense, current_row)
    worksheet.delete_rows(saved_expense.row_number)
    clear_budget_snapshot_cache()


def get_recent_expenses(limit: int = 5) -> list[tuple[str, str, str, str, str, str]]:
    if limit <= 0:
        return []

    spreadsheet = get_spreadsheet()
    worksheet = find_worksheet_case_insensitive(spreadsheet, EXPENSES_SHEET_NAME)
    last_row = len(worksheet.col_values(1))
    if last_row <= 1:
        return []

    tail_size = max(limit * 3, limit + 5)
    start_row = max(2, last_row - tail_size + 1)
    rows = worksheet.get(f"A{start_row}:G{last_row}") or []

    expenses: list[tuple[str, str, str, str, str, str]] = []
    for row in rows:
        date_value = row[0].strip() if len(row) > 0 else ""
        username_value = row[2].strip() if len(row) > 2 else ""
        category_value = row[3].strip() if len(row) > 3 else ""
        subcategory_value = row[4].strip() if len(row) > 4 else ""
        amount_value = row[5].strip() if len(row) > 5 else ""
        comment_value = row[6].strip() if len(row) > 6 else ""

        if not (date_value and subcategory_value and amount_value):
            continue

        expenses.append(
            (
                date_value,
                username_value,
                category_value,
                subcategory_value,
                amount_value,
                comment_value,
            )
        )

    return expenses[-limit:]


def _get_expenses_worksheet() -> gspread.Worksheet:
    spreadsheet = get_spreadsheet()
    return find_worksheet_case_insensitive(spreadsheet, EXPENSES_SHEET_NAME)


def _get_expense_row_values(worksheet: gspread.Worksheet, row_number: int) -> list[str]:
    rows = worksheet.get(f"A{row_number}:H{row_number}") or []
    if not rows:
        raise StaleExpenseError("Expense row no longer exists.")

    row = list(rows[0])
    if len(row) < 8:
        row.extend([""] * (8 - len(row)))
    return row


def _assert_same_saved_expense(saved_expense: SavedExpense, row: list[str]) -> None:
    date_value = row[0].strip() if len(row) > 0 else ""
    month_key = row[1].strip() if len(row) > 1 else ""
    username = row[2].strip() if len(row) > 2 else ""
    category = row[3].strip() if len(row) > 3 else ""
    subcategory = row[4].strip() if len(row) > 4 else ""
    amount = row[5].strip() if len(row) > 5 else ""
    comment = row[6].strip() if len(row) > 6 else ""
    expense_id = row[7].strip() if len(row) > 7 else ""

    if date_value != saved_expense.date:
        raise StaleExpenseError("Expense row changed or moved.")
    if month_key != saved_expense.month_key:
        raise StaleExpenseError("Expense row changed or moved.")
    if username != saved_expense.username:
        raise StaleExpenseError("Expense row changed or moved.")
    if category != saved_expense.category:
        raise StaleExpenseError("Expense row changed or moved.")
    if subcategory != saved_expense.subcategory:
        raise StaleExpenseError("Expense row changed or moved.")
    if _normalize_amount_for_compare(amount) != _normalize_amount_for_compare(saved_expense.amount):
        raise StaleExpenseError("Expense row changed or moved.")
    if comment != saved_expense.comment:
        raise StaleExpenseError("Expense row changed or moved.")
    if expense_id != saved_expense.expense_id:
        raise StaleExpenseError("Expense row changed or moved.")


def _normalize_amount_for_compare(value: str) -> Decimal:
    normalized = value.strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    if not normalized:
        return Decimal("0")
    return Decimal(normalized).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
