from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from services import google_sheets


class ProfileSheetsTests(unittest.TestCase):
    def test_profile_open_does_not_mutate_active_adapter(self):
        active_client, active_sheet, active_cache = object(), object(), {}
        with patch.object(google_sheets, "_client", active_client), \
             patch.object(google_sheets, "_spreadsheet", active_sheet), \
             patch.object(google_sheets, "_worksheet_cache", active_cache), \
             patch.object(google_sheets.gspread, "service_account") as service:
            google_sheets.open_profile_spreadsheet(SimpleNamespace(spreadsheet_id="third"), "test-key")
            service.assert_called_once_with(filename="test-key")
            service.return_value.open_by_key.assert_called_once_with("third")
            self.assertIs(google_sheets._client, active_client)
            self.assertIs(google_sheets._spreadsheet, active_sheet)
            self.assertIs(google_sheets._worksheet_cache, active_cache)
