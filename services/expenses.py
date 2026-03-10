from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import gspread

from constants import EXPENSES_SHEET_NAME
from services.google_sheets import find_worksheet_case_insensitive, get_spreadsheet


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


def _get_next_expense_row(worksheet: gspread.Worksheet) -> int:
    all_rows = worksheet.get_all_values()
    last_filled_row = 1

    for idx, row in enumerate(all_rows[1:], start=2):
        a = row[0].strip() if len(row) > 0 else ""
        b = row[1].strip() if len(row) > 1 else ""
        c = row[2].strip() if len(row) > 2 else ""
        d = row[3].strip() if len(row) > 3 else ""
        e = row[4].strip() if len(row) > 4 else ""
        f = row[5].strip() if len(row) > 5 else ""
        if any([a, b, c, d, e, f]):
            last_filled_row = idx

    return last_filled_row + 1


def write_expense(
    username: str,
    category: str,
    subcategory: str,
    amount: str,
    comment: str = "",
) -> None:
    spreadsheet = get_spreadsheet()
    worksheet = find_worksheet_case_insensitive(spreadsheet, EXPENSES_SHEET_NAME)
    next_row = _get_next_expense_row(worksheet)
    today = datetime.now().strftime("%d.%m.%y")

    worksheet.update(
        f"A{next_row}:F{next_row}",
        [[today, username, category, subcategory, amount, comment]],
        raw=False,
    )


def get_recent_expenses(limit: int = 5) -> list[tuple[str, str, str, str, str, str]]:
    if limit <= 0:
        return []

    spreadsheet = get_spreadsheet()
    worksheet = find_worksheet_case_insensitive(spreadsheet, EXPENSES_SHEET_NAME)
    all_rows = worksheet.get_all_values()

    expenses: list[tuple[str, str, str, str, str, str]] = []
    for row in all_rows[1:]:
        date_value = row[0].strip() if len(row) > 0 else ""
        username_value = row[1].strip() if len(row) > 1 else ""
        category_value = row[2].strip() if len(row) > 2 else ""
        subcategory_value = row[3].strip() if len(row) > 3 else ""
        amount_value = row[4].strip() if len(row) > 4 else ""
        comment_value = row[5].strip() if len(row) > 5 else ""

        if not (date_value and username_value and subcategory_value and amount_value):
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
