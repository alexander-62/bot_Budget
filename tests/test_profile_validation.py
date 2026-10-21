from dataclasses import replace
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from services.bot_profiles import BotProfile
from services.profile_validation import validate_profile, normalize_spreadsheet_id, telegram_identity
from google.auth.exceptions import MalformedError, RefreshError, TransportError
from gspread.exceptions import APIError, SpreadsheetNotFound
from requests.exceptions import Timeout


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.profile = BotProfile("family", "Family", "sheet-family")
        self.token = "123:private-token"

    def test_success_and_duplicate_identity(self):
        check_sheets = Mock()
        result = validate_profile(self.profile, self.token, check_telegram=lambda _: 123, check_sheets=check_sheets)
        self.assertTrue(result.ok)
        check_sheets.assert_called_once()
        other = BotProfile("other", "Other", "sheet-other")
        result = validate_profile(self.profile, self.token, profiles=[other], token_loader=lambda _: "123:rotated", check_telegram=lambda _: 123, check_sheets=check_sheets)
        self.assertFalse(result.ok)
        self.assertIn("Telegram", result.message)

    def test_transport_failures_never_reveal_token(self):
        for target in ("telegram", "sheets"):
            failure = Mock(side_effect=RuntimeError(self.token))
            result = validate_profile(self.profile, self.token,
                                      check_telegram=failure if target == "telegram" else lambda _: 123,
                                      check_sheets=failure if target == "sheets" else Mock())
            self.assertFalse(result.ok)
            self.assertNotIn(self.token, result.message)
        with patch("services.profile_validation.urlopen", side_effect=OSError(self.token)):
            with self.assertRaises(ValueError) as error:
                telegram_identity(self.token)
            self.assertNotIn(self.token, str(error.exception))
            self.assertTrue(error.exception.__suppress_context__)

    def test_invalid_fields_fail_before_network(self):
        check = Mock()
        result = validate_profile(replace(self.profile, timezone="invalid-zone"), self.token, check_telegram=check)
        self.assertFalse(result.ok)
        check.assert_not_called()

    def test_shared_table_and_url(self):
        self.assertEqual(normalize_spreadsheet_id("https://docs.google.com/spreadsheets/d/abc-123/edit"), "abc-123")
        result = validate_profile(self.profile, self.token, profiles=[replace(self.profile, id="other")], check_telegram=lambda _: 123)
        self.assertFalse(result.ok)

    def test_specific_sheets_failures_are_actionable_without_raw_error_text(self):
        def api(code, reason=None):
            response = Mock()
            response.json.return_value = {"error": {"code": code, "message": self.token,
                                                   "details": [{"reason": reason}] if reason else []}}
            return APIError(response)
        wrapped = PermissionError(self.token)
        wrapped.__cause__ = api(403)
        cases = [
            (FileNotFoundError(self.token), "не найден"),
            (IsADirectoryError(self.token), "папка"),
            (PermissionError(self.token), "чтение файла"),
            (SpreadsheetNotFound(self.token), "ссылку/ID"),
            (wrapped, "Редактор"),
            (api(403), "Редактор"),
            (api(403, "SERVICE_DISABLED"), "включите Google Sheets API"),
            (api(401), "действующий"),
            (api(429), "лимит"),
            (api(503), "временно недоступен"),
            (json.JSONDecodeError(self.token, "", 0), "JSON-ключ"),
            (MalformedError(self.token), "JSON-ключ"),
            (RefreshError(self.token), "авторизацию"),
            (TransportError(self.token), "интернет"),
            (Timeout(self.token), "интернет"),
        ]
        for error, expected in cases:
            with self.subTest(error=type(error).__name__, expected=expected):
                result = validate_profile(self.profile, self.token, check_telegram=lambda _: 123,
                                          check_sheets=Mock(side_effect=error))
                self.assertFalse(result.ok)
                self.assertIn(expected, result.message)
                self.assertNotIn(self.token, result.message)

    def test_blank_key_field_uses_common_configured_key(self):
        check = Mock()
        with patch("services.profile_validation.get_credentials_path", return_value=Path("shared-key.json")):
            result = validate_profile(self.profile, self.token, check_telegram=lambda _: 123, check_sheets=check)
        self.assertTrue(result.ok)
        self.assertEqual(check.call_args.args[1].name, "shared-key.json")
