import sys
import types
import unittest
from datetime import date
from decimal import Decimal
from unittest import mock

from constants import EXPENSES_SHEET_NAME, USERS_SHEET_NAME


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

from services import daily_digest, google_sheets


class FakeWorksheet:
    def __init__(self, title: str, rows: list[list[str]]) -> None:
        self.title = title
        self.rows = rows
        self.updated_cells: list[tuple[int, int, str]] = []

    def get_all_values(self):
        return [list(row) for row in self.rows]

    def update_cell(self, row: int, column: int, value: str):
        while len(self.rows[row - 1]) < column:
            self.rows[row - 1].append("")
        self.rows[row - 1][column - 1] = value
        self.updated_cells.append((row, column, value))


class FakeSpreadsheet:
    def __init__(self, worksheets: dict[str, FakeWorksheet]) -> None:
        self._worksheets = list(worksheets.values())

    def worksheets(self):
        return list(self._worksheets)


class DailyDigestTests(unittest.TestCase):
    def setUp(self) -> None:
        google_sheets.reset_google_sheets_cache()

    def tearDown(self) -> None:
        google_sheets.reset_google_sheets_cache()

    def test_recipients_default_enabled_and_skip_disabled_users(self) -> None:
        users = FakeWorksheet(
            USERS_SHEET_NAME,
            [
                ["username", "user_id", "digest_enabled", "last_digest_date"],
                ["alice", "101", "", ""],
                ["bob", "102", "нет", ""],
                ["carol", "103", "TRUE", "2026-07-08"],
                ["dave", "bad-id", "", ""],
            ],
        )
        spreadsheet = FakeSpreadsheet({USERS_SHEET_NAME: users})

        with mock.patch.object(daily_digest, "get_spreadsheet", return_value=spreadsheet):
            recipients = daily_digest.get_digest_recipients()

        self.assertEqual([recipient.username for recipient in recipients], ["alice", "carol"])
        self.assertEqual([recipient.chat_id for recipient in recipients], [101, 103])
        self.assertEqual(recipients[1].last_digest_date, "2026-07-08")

    def test_mark_digest_sent_updates_last_digest_date_column(self) -> None:
        users = FakeWorksheet(
            USERS_SHEET_NAME,
            [
                ["username", "user_id", "digest_enabled", "last_digest_date"],
                ["alice", "101", "", ""],
            ],
        )
        spreadsheet = FakeSpreadsheet({USERS_SHEET_NAME: users})

        with mock.patch.object(daily_digest, "get_spreadsheet", return_value=spreadsheet):
            daily_digest.mark_digest_sent(2, date(2026, 7, 9))

        self.assertEqual(users.updated_cells, [(2, 4, "2026-07-09")])

    def test_summary_groups_all_users_expenses_by_category_for_day(self) -> None:
        expenses = FakeWorksheet(
            EXPENSES_SHEET_NAME,
            [
                ["Дата", "Месяц", "Пользователь", "Категория", "Подкатегория", "Сумма", "Комментарий"],
                ["2026-07-09", "2026-07", "@alice", "Еда", "Кафе", "10,40", ""],
                ["2026-07-09", "2026-07", "@bob", "Транспорт", "Такси", "7.60", ""],
                ["09.07.26", "2026-07", "@carol", "Еда", "Продукты", "5", ""],
                ["2026-07-08", "2026-07", "@alice", "Дом", "Хозтовары", "100", ""],
                ["2026-07-09", "2026-07", "@alice", "Еда", "Кафе", "bad", ""],
            ],
        )
        spreadsheet = FakeSpreadsheet({EXPENSES_SHEET_NAME: expenses})

        with mock.patch.object(daily_digest, "get_spreadsheet", return_value=spreadsheet):
            summary = daily_digest.build_daily_digest_summary(date(2026, 7, 9))

        self.assertEqual(
            summary.category_totals,
            (
                ("Еда", Decimal("15.40")),
                ("Транспорт", Decimal("7.60")),
            ),
        )

    def test_format_message_for_empty_day_is_still_a_reminder(self) -> None:
        summary = daily_digest.DailyDigestSummary(date(2026, 7, 9), tuple())

        message = daily_digest.format_daily_digest_message(summary)

        self.assertIn("Сегодня пока не записали ни одной траты.", message)
        self.assertIn("Не забыли ли мы что-то записать?", message)


if __name__ == "__main__":
    unittest.main()
