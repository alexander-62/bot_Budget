import sys
import types
import unittest
from unittest import mock

from constants import CATEGORIES_SHEET_NAME, EXPENSES_SHEET_NAME, LIMITS_SHEET_NAME, SHOPPING_SHEET_NAME


if "gspread" not in sys.modules:
    fake_gspread = types.ModuleType("gspread")

    class _Client:  # pragma: no cover - placeholder for annotations
        pass

    class _Spreadsheet:  # pragma: no cover - placeholder for annotations
        pass

    class _Worksheet:  # pragma: no cover - placeholder for annotations
        pass

    fake_gspread.Client = _Client
    fake_gspread.Spreadsheet = _Spreadsheet
    fake_gspread.Worksheet = _Worksheet
    fake_gspread.service_account = lambda filename=None: None
    sys.modules["gspread"] = fake_gspread

from services import budget, expenses, google_sheets, shopping


class FakeWorksheet:
    def __init__(self, title: str, rows: list[list[str]] | None = None) -> None:
        self.title = title
        self._rows = rows or []
        self.all_values_calls = 0
        self.col_values_calls = 0
        self.get_calls: list[str] = []
        self.append_rows_calls: list[list[list[str]]] = []

    def get_all_values(self):
        self.all_values_calls += 1
        return [list(row) for row in self._rows]

    def col_values(self, column: int):
        self.col_values_calls += 1
        if column != 1:
            raise AssertionError(f"Unexpected column request: {column}")
        return [row[0] if row else "" for row in self._rows]

    def get(self, range_name: str):
        self.get_calls.append(range_name)
        start_text, end_text = range_name.split(":")
        start_row = int("".join(ch for ch in start_text if ch.isdigit()))
        end_row = int("".join(ch for ch in end_text if ch.isdigit()))
        start_idx = max(start_row - 1, 0)
        end_idx = min(end_row, len(self._rows))
        return [list(row) for row in self._rows[start_idx:end_idx]]

    def append_rows(self, values, value_input_option="RAW"):
        self.append_rows_calls.append([list(row) for row in values])
        self._rows.extend([list(row) for row in values])


class FakeSpreadsheet:
    def __init__(self, worksheets: dict[str, FakeWorksheet]) -> None:
        self._worksheets = list(worksheets.values())
        self._worksheets_by_title = worksheets
        self.worksheets_calls = 0

    def worksheets(self):
        self.worksheets_calls += 1
        return list(self._worksheets)


def _build_budget_spreadsheet() -> FakeSpreadsheet:
    categories = FakeWorksheet(
        CATEGORIES_SHEET_NAME,
        [
            ["Категория", "Подкатегория", "Активно", "Порядок"],
            ["Еда", "Продукты", "да", "1"],
            ["Еда", "Кафе", "yes", "2"],
            ["Дом", "Ремонт", "1", "3"],
        ],
    )
    limits = FakeWorksheet(
        LIMITS_SHEET_NAME,
        [
            ["Категория", "Подкатегория", "2026-06"],
            ["Еда", "Продукты", "100"],
            ["Еда", "Кафе", "50"],
            ["Дом", "Ремонт", "25"],
        ],
    )
    expenses_sheet = FakeWorksheet(
        EXPENSES_SHEET_NAME,
        [
            ["Дата", "Месяц", "Пользователь", "Категория", "Подкатегория", "Сумма", "Комментарий"],
            ["2026-06-01", "2026-06", "@alice", "Еда", "Продукты", "20", ""],
            ["2026-06-02", "2026-06", "@bob", "Еда", "Кафе", "10", ""],
            ["2026-06-03", "2026-06", "@bob", "Еда", "Продукты", "5", ""],
        ],
    )
    return FakeSpreadsheet(
        {
            CATEGORIES_SHEET_NAME: categories,
            LIMITS_SHEET_NAME: limits,
            EXPENSES_SHEET_NAME: expenses_sheet,
        }
    )


class Phase2ReadPathTests(unittest.TestCase):
    def setUp(self) -> None:
        google_sheets.reset_google_sheets_cache()
        budget.clear_budget_snapshot_cache()

    def tearDown(self) -> None:
        google_sheets.reset_google_sheets_cache()
        budget.clear_budget_snapshot_cache()

    def test_budget_views_share_one_snapshot_until_cleared(self) -> None:
        spreadsheet = _build_budget_spreadsheet()

        with mock.patch.object(budget, "get_spreadsheet", return_value=spreadsheet):
            total_limit, categories = budget.get_budget_limits()
            month_limit, month_spent, month_remaining = budget.get_month_totals()
            category_title, category_limit, category_spent, category_remaining, subcategories = budget.get_category_details(
                "Еда"
            )

            self.assertEqual(total_limit, "175,00")
            self.assertEqual(categories, ["Еда", "Дом"])
            self.assertEqual(month_limit, "175,00")
            self.assertEqual(month_spent, "35,00")
            self.assertEqual(month_remaining, "140,00")
            self.assertEqual(category_title, "Еда")
            self.assertEqual(category_limit, "150,00")
            self.assertEqual(category_spent, "35,00")
            self.assertEqual(category_remaining, "115,00")
            self.assertEqual([name for name, *_ in subcategories], ["Продукты", "Кафе"])

            categories_ws = spreadsheet._worksheets_by_title[CATEGORIES_SHEET_NAME]
            limits_ws = spreadsheet._worksheets_by_title[LIMITS_SHEET_NAME]
            expenses_ws = spreadsheet._worksheets_by_title[EXPENSES_SHEET_NAME]

            self.assertEqual(categories_ws.all_values_calls, 1)
            self.assertEqual(limits_ws.all_values_calls, 1)
            self.assertEqual(expenses_ws.all_values_calls, 1)

            budget.clear_budget_snapshot_cache()
            budget.get_budget_limits()

            self.assertEqual(categories_ws.all_values_calls, 2)
            self.assertEqual(limits_ws.all_values_calls, 2)
            self.assertEqual(expenses_ws.all_values_calls, 2)

    def test_recent_expenses_reads_bounded_tail_range(self) -> None:
        rows = [["Дата", "Месяц", "Пользователь", "Категория", "Подкатегория", "Сумма", "Комментарий"]]
        for idx in range(1, 13):
            rows.append(
                [
                    f"2026-06-{idx:02d}",
                    "2026-06",
                    f"@user{idx}",
                    "Еда",
                    f"Подкатегория {idx}",
                    str(idx),
                    "" if idx % 2 else f"Комментарий {idx}",
                ]
            )

        expenses_sheet = FakeWorksheet(EXPENSES_SHEET_NAME, rows)
        spreadsheet = FakeSpreadsheet({EXPENSES_SHEET_NAME: expenses_sheet})

        with mock.patch.object(expenses, "get_spreadsheet", return_value=spreadsheet):
            recent = expenses.get_recent_expenses(limit=3)

        self.assertEqual(
            recent,
            [
                ("2026-06-10", "@user10", "Еда", "Подкатегория 10", "10", "Комментарий 10"),
                ("2026-06-11", "@user11", "Еда", "Подкатегория 11", "11", ""),
                ("2026-06-12", "@user12", "Еда", "Подкатегория 12", "12", "Комментарий 12"),
            ],
        )
        self.assertEqual(expenses_sheet.col_values_calls, 1)
        self.assertEqual(len(expenses_sheet.get_calls), 1)
        start_row = int(expenses_sheet.get_calls[0].split(":")[0][1:])
        self.assertGreater(start_row, 2)

    def test_shopping_batch_add_reads_once_and_appends_once(self) -> None:
        shopping_sheet = FakeWorksheet(
            SHOPPING_SHEET_NAME,
            [
                ["Список"],
                ["Bread"],
                ["Milk"],
            ],
        )
        spreadsheet = FakeSpreadsheet({SHOPPING_SHEET_NAME: shopping_sheet})

        with mock.patch.object(shopping, "get_spreadsheet", return_value=spreadsheet):
            added, existing = shopping.add_shopping_items(["milk", "Eggs", " eggs ", "Bread"])

        self.assertEqual(added, ["Eggs"])
        self.assertEqual(existing, ["Milk", "Eggs", "Bread"])
        self.assertEqual(shopping_sheet.col_values_calls, 1)
        self.assertEqual(shopping_sheet.append_rows_calls, [[["Eggs"]]])


if __name__ == "__main__":
    unittest.main()
