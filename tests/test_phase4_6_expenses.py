import sys
import types
import unittest
from unittest import mock


if "gspread" not in sys.modules:
    fake_gspread = types.ModuleType("gspread")

    class _Client:
        pass

    class _Spreadsheet:
        pass

    class _Worksheet:
        pass

    fake_gspread.Client = _Client
    fake_gspread.Spreadsheet = _Spreadsheet
    fake_gspread.Worksheet = _Worksheet
    fake_gspread.service_account = lambda filename=None: None
    sys.modules["gspread"] = fake_gspread

from services import budget, expenses, google_sheets


class FakeWorksheet:
    def __init__(self, title: str, rows: list[list[str]] | None = None) -> None:
        self.title = title
        self.rows = rows or []
        self.append_row_calls: list[list[str]] = []
        self.update_calls: list[tuple[str, list[list[object]], bool]] = []
        self.delete_rows_calls: list[int] = []

    def append_row(self, values, value_input_option="RAW", insert_data_option=None, table_range=None):
        self.append_row_calls.append(list(values))
        self.rows.append([str(value) for value in values])
        row_number = len(self.rows)
        return {"updates": {"updatedRange": f"{self.title}!A{row_number}:H{row_number}"}}

    def col_values(self, column: int):
        index = column - 1
        return [row[index] if len(row) > index else "" for row in self.rows]

    def get(self, range_name: str):
        start_text, end_text = range_name.split(":")
        start_row = int("".join(ch for ch in start_text if ch.isdigit()))
        end_row = int("".join(ch for ch in end_text if ch.isdigit()))
        start_idx = max(start_row - 1, 0)
        end_idx = min(end_row, len(self.rows))
        return [list(row) for row in self.rows[start_idx:end_idx]]

    def update(self, range_name: str, values, raw=False):
        self.update_calls.append((range_name, values, raw))
        row_number = int("".join(ch for ch in range_name.split(":")[0] if ch.isdigit()))
        self.rows[row_number - 1] = [str(value) for value in values[0]]

    def delete_rows(self, row_number: int):
        self.delete_rows_calls.append(row_number)
        self.rows.pop(row_number - 1)


class FakeSpreadsheet:
    def __init__(self, worksheet: FakeWorksheet) -> None:
        self._worksheet = worksheet

    def worksheets(self):
        return [self._worksheet]


class ExpenseServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        google_sheets.reset_google_sheets_cache()
        budget.clear_budget_snapshot_cache()

    def tearDown(self) -> None:
        google_sheets.reset_google_sheets_cache()
        budget.clear_budget_snapshot_cache()

    def test_parse_amount_with_optional_comment_keeps_existing_formats(self) -> None:
        self.assertEqual(expenses.parse_amount("12,345"), "12,35")
        self.assertEqual(
            expenses.parse_amount_with_optional_comment("12,5 кофе с собой"),
            ("12,50", "кофе с собой"),
        )

        with self.assertRaises(ValueError):
            expenses.parse_amount_with_optional_comment("")

    def test_write_expense_uses_append_and_returns_saved_identity(self) -> None:
        worksheet = FakeWorksheet(
            "Траты_по_месяцам",
            [["Дата", "Месяц", "Пользователь", "Категория", "Подкатегория", "Сумма", "Комментарий", "expense_id"]],
        )
        spreadsheet = FakeSpreadsheet(worksheet)

        with mock.patch.object(expenses, "get_spreadsheet", return_value=spreadsheet):
            saved = expenses.write_expense("@alice", "Еда", "Кафе", "12,50", "латте")

        self.assertEqual(saved.row_number, 2)
        self.assertEqual(saved.category, "Еда")
        self.assertEqual(saved.subcategory, "Кафе")
        self.assertEqual(saved.amount, "12,50")
        self.assertEqual(saved.comment, "латте")
        self.assertTrue(saved.expense_id)
        self.assertEqual(len(worksheet.append_row_calls), 1)
        self.assertEqual(worksheet.append_row_calls[0][7], saved.expense_id)

    def test_update_expense_rejects_stale_identity(self) -> None:
        saved = expenses.SavedExpense(
            expense_id="abc123",
            sheet_name="Траты_по_месяцам",
            row_number=2,
            row_range="Траты_по_месяцам!A2:H2",
            date="2026-06-29",
            month_key="2026-06",
            username="@alice",
            category="Еда",
            subcategory="Кафе",
            amount="12,50",
            comment="латте",
        )
        worksheet = FakeWorksheet(
            "Траты_по_месяцам",
            [
                ["Дата", "Месяц", "Пользователь", "Категория", "Подкатегория", "Сумма", "Комментарий", "expense_id"],
                ["2026-06-29", "2026-06", "@alice", "Еда", "Кафе", "12.5", "латте", "other-id"],
            ],
        )
        spreadsheet = FakeSpreadsheet(worksheet)

        with mock.patch.object(expenses, "get_spreadsheet", return_value=spreadsheet):
            with self.assertRaises(expenses.StaleExpenseError):
                expenses.update_expense(saved, "15,00", "капучино")


if __name__ == "__main__":
    unittest.main()
