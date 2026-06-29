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

if "aiogram" not in sys.modules:
    fake_aiogram = types.ModuleType("aiogram")
    fake_aiogram.__path__ = []
    fake_types = types.ModuleType("aiogram.types")
    fake_types.Message = object
    fake_types.CallbackQuery = object
    fake_aiogram.types = fake_types
    sys.modules["aiogram"] = fake_aiogram
    sys.modules["aiogram.types"] = fake_types

from constants import CATEGORIES_SHEET_NAME, EXPENSES_SHEET_NAME, LIMITS_SHEET_NAME, USERS_SHEET_NAME
from services import access, google_sheets, startup_validation


class FakeWorksheet:
    def __init__(self, title: str, rows: list[list[str]]) -> None:
        self.title = title
        self.rows = rows
        self.updated_cells: list[tuple[int, int, str]] = []

    def col_values(self, column: int):
        index = column - 1
        return [row[index] if len(row) > index else "" for row in self.rows]

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


class AccessAndStartupTests(unittest.TestCase):
    def setUp(self) -> None:
        google_sheets.reset_google_sheets_cache()
        access._allowed_usernames_cache = set()
        access._allowed_usernames_cache_ts = 0.0
        access._allowed_chat_ids_cache = set()
        access._allowed_chat_ids_cache_ts = 0.0
        access._allowed_user_chat_ids_cache = {}
        access._allowed_user_chat_ids_cache_ts = 0.0

    def tearDown(self) -> None:
        google_sheets.reset_google_sheets_cache()

    def test_access_loader_ignores_headers_and_malformed_chat_ids(self) -> None:
        users = FakeWorksheet(
            USERS_SHEET_NAME,
            [
                ["username", "user_id"],
                ["Alice", "101"],
                ["Bob", "abc"],
                ["", ""],
            ],
        )
        spreadsheet = FakeSpreadsheet({USERS_SHEET_NAME: users})

        with mock.patch.object(access, "get_spreadsheet", return_value=spreadsheet):
            usernames = access.get_allowed_usernames()
            chat_ids = access.get_allowed_chat_ids()

        self.assertEqual(usernames, {"alice", "bob"})
        self.assertEqual(chat_ids, {101})

    def test_sync_allowed_user_chat_id_updates_existing_user(self) -> None:
        users = FakeWorksheet(
            USERS_SHEET_NAME,
            [
                ["username", "user_id"],
                ["alice", ""],
            ],
        )
        spreadsheet = FakeSpreadsheet({USERS_SHEET_NAME: users})

        with mock.patch.object(access, "get_spreadsheet", return_value=spreadsheet):
            access.sync_allowed_user_chat_id("Alice", 555)

        self.assertEqual(users.updated_cells, [(2, 2, "555")])

    def test_startup_validation_fails_on_missing_required_header(self) -> None:
        spreadsheet = FakeSpreadsheet(
            {
                USERS_SHEET_NAME: FakeWorksheet(USERS_SHEET_NAME, [["username"]]),
                CATEGORIES_SHEET_NAME: FakeWorksheet(CATEGORIES_SHEET_NAME, [["Категория", "Подкатегория", "Активно"]]),
                LIMITS_SHEET_NAME: FakeWorksheet(LIMITS_SHEET_NAME, [["Категория", "Подкатегория"]]),
                EXPENSES_SHEET_NAME: FakeWorksheet(
                    EXPENSES_SHEET_NAME,
                    [["Дата", "Месяц", "Пользователь", "Категория", "Подкатегория", "Сумма"]],
                ),
                "Список покупок Продукты": FakeWorksheet("Список покупок Продукты", [["Список"]]),
            }
        )

        with mock.patch.object(startup_validation, "get_spreadsheet", return_value=spreadsheet):
            with mock.patch.object(startup_validation, "_validate_config", return_value=None):
                with self.assertRaises(startup_validation.StartupValidationError):
                    startup_validation.validate_startup()


if __name__ == "__main__":
    unittest.main()
