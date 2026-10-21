from dataclasses import replace
import unittest
from unittest.mock import Mock, patch

from services.bot_profiles import BotProfile
from services.profile_validation import validate_profile, normalize_spreadsheet_id, telegram_identity


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
