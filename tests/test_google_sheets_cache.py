import unittest
import sys
import types
from unittest import mock


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

from services import google_sheets


class FakeWorksheet:
    def __init__(self, title: str) -> None:
        self.title = title


class FakeSpreadsheet:
    def __init__(self) -> None:
        self.worksheets_calls = 0
        self._worksheets = [FakeWorksheet("Users"), FakeWorksheet("Categories")]

    def worksheets(self):
        self.worksheets_calls += 1
        return list(self._worksheets)


class FakeClient:
    def __init__(self, spreadsheet: FakeSpreadsheet) -> None:
        self.spreadsheet = spreadsheet
        self.open_calls = 0

    def open_by_key(self, spreadsheet_id: str):
        self.open_calls += 1
        self.last_spreadsheet_id = spreadsheet_id
        return self.spreadsheet


class GoogleSheetsCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        google_sheets.reset_google_sheets_cache()

    def tearDown(self) -> None:
        google_sheets.reset_google_sheets_cache()

    def test_spreadsheet_and_worksheet_results_are_cached(self) -> None:
        spreadsheet = FakeSpreadsheet()
        client = FakeClient(spreadsheet)

        with mock.patch.object(google_sheets, "get_gspread_client", return_value=client):
            first = google_sheets.get_spreadsheet()
            second = google_sheets.get_spreadsheet()

        self.assertIs(first, spreadsheet)
        self.assertIs(second, spreadsheet)
        self.assertEqual(client.open_calls, 1)

        first_ws = google_sheets.find_worksheet_case_insensitive(first, " users ")
        second_ws = google_sheets.find_worksheet_case_insensitive(first, "Users")

        self.assertIs(first_ws, second_ws)
        self.assertEqual(spreadsheet.worksheets_calls, 1)

    def test_reset_clears_worksheet_cache(self) -> None:
        spreadsheet = FakeSpreadsheet()
        client = FakeClient(spreadsheet)

        with mock.patch.object(google_sheets, "get_gspread_client", return_value=client):
            google_sheets.get_spreadsheet()
            google_sheets.find_worksheet_case_insensitive(spreadsheet, "Users")

        self.assertEqual(spreadsheet.worksheets_calls, 1)
        google_sheets.reset_google_sheets_cache()

        next_ws = google_sheets.find_worksheet_case_insensitive(spreadsheet, "Users")
        self.assertEqual(next_ws.title, "Users")
        self.assertEqual(spreadsheet.worksheets_calls, 2)


if __name__ == "__main__":
    unittest.main()
