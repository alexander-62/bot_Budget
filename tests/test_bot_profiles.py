import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from services import bot_profiles as profiles
from services.money import format_money, parse_sheet_number


class BotProfileTests(unittest.TestCase):
    def setUp(self):
        original = Path.exists
        guard = patch.object(Path, "exists", lambda path: False if path.name == ".env" else original(path))
        guard.start()
        self.addCleanup(guard.stop)

    def test_legacy_default_and_runtime_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            personal = profiles.list_profiles(base)[0]
            self.assertTrue(personal.legacy)
            self.assertEqual(personal.runtime_dir(base), base)
            self.assertEqual(profiles.BotProfile("work", "Работа", "sheet", "RUB").runtime_dir(base), base / ".runtime" / "work")

    def test_registry_round_trip_and_duplicate_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            tokens = {}
            with patch.object(profiles, "load_token", side_effect=lambda key, _: tokens.get(key, "")), patch.object(profiles, "save_token", side_effect=lambda key, token, _: tokens.__setitem__(key, token)), patch.object(profiles, "get_profile_token", side_effect=lambda profile, _: tokens.get(profile.id, "")):
                work = profiles.BotProfile("work", "Работа", "sheet-work", "RUB")
                profiles.save_profile(work, token="123:fake", base_dir=base)
                self.assertEqual(profiles.get_profile("work", base), work)
                self.assertNotIn("123:fake", (base / "profiles.json").read_text(encoding="utf-8"))
                with self.assertRaises(ValueError):
                    profiles.save_profile(work, token="123:fake", base_dir=base)
                with self.assertRaises(ValueError):
                    profiles.save_profile(profiles.BotProfile("other", "Other", "sheet-other"), token="123:rotated", base_dir=base)
                with self.assertRaises(ValueError):
                    profiles.save_profile(profiles.BotProfile("other", "Other", "sheet-work"), token="456:fake", base_dir=base)
                edited = profiles.BotProfile("work", "Business", "sheet-work", "RUB", autostart=True)
                profiles.update_profile(edited, base_dir=base)
                self.assertTrue(profiles.get_profile("work", base).autostart)

    def test_invalid_id_cannot_escape_runtime_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                profiles.save_profile(profiles.BotProfile("../escape", "Bad", "sheet"), token="123:fake", base_dir=Path(directory))

    def test_unknown_profile_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                profiles.get_profile("unknown", Path(directory))

    def test_ruble_and_euro_presentation(self):
        self.assertEqual(format_money("1234,5", "RUB"), "1 235 ₽")
        self.assertEqual(format_money("1234,5", "EUR"), "1 235 €")
        self.assertEqual(parse_sheet_number("1 200,25 ₽"), parse_sheet_number("1200.25"))

    def test_profile_timezone_changes_month_at_utc_boundary(self):
        from services import budget
        instant = datetime(2026, 1, 31, 22, 30, tzinfo=timezone.utc)

        class Clock:
            @staticmethod
            def now(zone):
                return instant.astimezone(zone)

        with patch.object(budget, "datetime", Clock), patch.object(budget, "BOT_TIMEZONE", "Europe/Moscow"):
            self.assertEqual(budget.get_current_month_key(), "2026-02")
        with patch.object(budget, "datetime", Clock), patch.object(budget, "BOT_TIMEZONE", "UTC"):
            self.assertEqual(budget.get_current_month_key(), "2026-01")


class NumericAccessTests(unittest.TestCase):
    def test_new_profile_accepts_id_without_username_and_rejects_reused_name(self):
        original = Path.exists
        with patch.object(Path, "exists", lambda path: False if path.name == ".env" else original(path)):
            from services import access
        profile = profiles.BotProfile("business", "Business", "sheet", "RUB")
        with patch.object(access, "PROFILE", profile), patch.object(access, "get_allowed_chat_ids", return_value={42}), patch.object(access, "get_allowed_usernames", side_effect=AssertionError("Username lookup forbidden")):
            self.assertEqual(access.is_allowed_user(42, None), (True, None))
            self.assertFalse(access.is_allowed_user(43, "known")[0])


if __name__ == "__main__":
    unittest.main()
