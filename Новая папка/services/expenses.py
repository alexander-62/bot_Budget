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

