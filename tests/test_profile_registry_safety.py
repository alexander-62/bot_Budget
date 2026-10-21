from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

from services import bot_profiles as profiles


class RegistrySafetyTests(unittest.TestCase):
    def setUp(self):
        original = Path.exists
        guard = patch.object(Path, "exists", lambda path: False if path.name == ".env" else original(path))
        guard.start()
        self.addCleanup(guard.stop)
        # Import a generated legacy config before fake crypto is installed.
        # A migrated local personal profile must never be decrypted by a test.
        with patch.object(profiles, "get_profile", return_value=profiles.BotProfile("personal", "Personal", "", legacy=True)):
            __import__("config")
        crypto = patch("services.profile_secrets._crypt", side_effect=lambda data, **kwargs: data[::-1])
        crypto.start()
        self.addCleanup(crypto.stop)

    def test_empty_registry_returns_personal_but_corruption_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            path = base / "profiles.json"
            path.write_text('{"profiles": []}', encoding="utf-8")
            self.assertTrue(profiles.list_profiles(base)[0].legacy)
            for malformed in ('{broken', '{"profiles": [{"id": "a", "name": null, "spreadsheet_id": "s"}]}'):
                path.write_text(malformed, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "profiles.json"):
                    profiles.save_profile(profiles.BotProfile("work", "Work", "sheet"), token="123:fake", base_dir=base)
                self.assertEqual(path.read_text(encoding="utf-8"), malformed)

    def test_failed_registry_commit_restores_previous_encrypted_token(self):
        from services import profile_secrets
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            profile = profiles.BotProfile("work", "Work", "sheet")
            with patch.object(profiles, "get_profile_token", return_value=""):
                profiles.save_profile(profile, token="123:old_fake", base_dir=base)
            before = (base / "profiles.json").read_bytes()
            encrypted = (base / ".profile-secrets" / "work.bin").read_bytes()
            replace = profiles.os.replace

            def fail_registry(source, target):
                if Path(target).name == "profiles.json":
                    raise OSError("generated registry failure")
                return replace(source, target)

            with patch.object(profiles.os, "replace", side_effect=fail_registry), patch.object(profiles, "get_profile_token", return_value=""):
                with self.assertRaises(OSError):
                    profiles.update_profile(profile, token="123:new_fake", base_dir=base)
            self.assertEqual((base / "profiles.json").read_bytes(), before)
            self.assertEqual((base / ".profile-secrets" / "work.bin").read_bytes(), encrypted)
            self.assertEqual(profile_secrets.load_token("work", base), "123:old_fake")
            self.assertFalse(list(base.glob(".profiles-*.tmp")))

    def test_concurrent_writers_preserve_both_profiles(self):
        entered, release = Event(), Event()
        original_save = profiles.save_token

        def delayed_save(profile_id, token, base):
            if profile_id == "first":
                entered.set()
                if not release.wait(3):
                    raise RuntimeError("Test synchronization timed out")
            original_save(profile_id, token, base)

        with tempfile.TemporaryDirectory() as directory, patch.object(profiles, "save_token", side_effect=delayed_save), patch.object(profiles, "get_profile_token", return_value=""):
            base = Path(directory)
            with ThreadPoolExecutor(max_workers=2) as executor:
                first = executor.submit(profiles.save_profile, profiles.BotProfile("first", "First", "sheet-first"), token="123:fake", base_dir=base)
                self.assertTrue(entered.wait(2))
                second = executor.submit(profiles.save_profile, profiles.BotProfile("second", "Second", "sheet-second"), token="456:fake", base_dir=base)
                release.set()
                first.result(timeout=4)
                second.result(timeout=4)
            self.assertEqual({p.id for p in profiles.list_profiles(base)}, {"personal", "first", "second"})

    def test_shared_header_validation_enforces_positions_and_expense_identity(self):
        from services.startup_validation import _WORKSHEET_RULES, validate_worksheet_header
        from constants import EXPENSES_SHEET_NAME
        for rule in _WORKSHEET_RULES:
            values = list(rule.required_headers)
            validate_worksheet_header(rule, values, legacy=True)
            if len(values) >= 2:
                values[0], values[1] = values[1], values[0]
                with self.assertRaises(ValueError):
                    validate_worksheet_header(rule, values, legacy=True)
        expense = next(rule for rule in _WORKSHEET_RULES if rule.name == EXPENSES_SHEET_NAME)
        with self.assertRaises(ValueError):
            validate_worksheet_header(expense, expense.required_headers, legacy=False)
        validate_worksheet_header(expense, (*expense.required_headers, "Комментарий", "expense_id"), legacy=False)


if __name__ == "__main__":
    unittest.main()
