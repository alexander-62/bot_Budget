"""Profile runtime checks using only generated configuration and fake credentials."""
import asyncio
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from services.bot_profiles import BotProfile
from services import profile_secrets

ROOT = Path(__file__).resolve().parents[1]


class ProfileRuntimeTests(unittest.TestCase):
    def test_implicit_personal_config_survives_malformed_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "config.py").write_text((ROOT / "config.py").read_text(encoding="utf-8"), encoding="utf-8")
            (base / ".env").write_text("GOOGLE_CREDENTIALS_FILE=generated-key.json\n", encoding="utf-8")
            (base / "profiles.json").write_text("{invalid", encoding="utf-8")
            env = {key: value for key, value in os.environ.items() if key != "BOT_BUDGET_PROFILE"}
            code = "import sys; sys.path.insert(0,sys.argv[1]); import config; assert config.PROFILE.legacy"
            subprocess.run([sys.executable, "-c", code, str(base)], cwd=ROOT, env=env, capture_output=True, check=True)

    def test_new_profile_never_uses_personal_token_or_table_and_shares_only_key(self):
        for credentials in ("", "own-key.json"):
            with self.subTest(credentials=credentials), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                (base / "config.py").write_text((ROOT / "config.py").read_text(encoding="utf-8"), encoding="utf-8")
                (base / ".env").write_text("BOT_TOKEN=111:personal_fake\nSPREADSHEET_ID=personal-table\nGOOGLE_CREDENTIALS_FILE=common-key.json\n", encoding="utf-8")
                profile = BotProfile("business", "Business", "business-table", "RUB", credentials_file=credentials)
                (base / "profiles.json").write_text(json.dumps({"profiles": [asdict(profile)]}), encoding="utf-8")
                env = {key: value for key, value in os.environ.items() if not key.startswith("BOT_BUDGET_") and key not in {"BOT_TOKEN", "SPREADSHEET_ID", "GOOGLE_CREDENTIALS_FILE", "WEBAPP_PORT"}}
                env["PYTHONUTF8"] = "1"
                env["BOT_BUDGET_PROFILE"] = "business"
                code = """import sys, json
sys.path.insert(0, sys.argv[1])
from unittest.mock import patch
with patch('services.profile_secrets.load_token', return_value=''):
 import config
 print(json.dumps([config.BOT_TOKEN,config.SPREADSHEET_ID,config.GOOGLE_CREDENTIALS_FILE,config.CURRENCY,str(config.PROFILE_RUNTIME_DIR)]))
"""
                result = subprocess.run([sys.executable, "-c", code, str(base)], cwd=ROOT, env=env, text=True, encoding="utf-8", capture_output=True, check=True)
                token, table, key, currency, runtime = json.loads(result.stdout)
                self.assertEqual(token, "")
                self.assertEqual(table, "business-table")
                self.assertEqual(key, credentials or "common-key.json")
                self.assertEqual(currency, "RUB")
                self.assertEqual(Path(runtime).resolve(), (base / ".runtime" / "business").resolve())

    def test_managed_personal_uses_registry_and_protected_token_without_profile_env(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "config.py").write_text((ROOT / "config.py").read_text(encoding="utf-8"), encoding="utf-8")
            (base / ".env").write_text("BOT_TOKEN=111:old_fake\nSPREADSHEET_ID=old-table\nGOOGLE_CREDENTIALS_FILE=common.json\n", encoding="utf-8")
            profile = BotProfile("personal", "Personal", "managed-table", "RUB", legacy=True, managed_settings=True, credentials_file="own.json")
            (base / "profiles.json").write_text(json.dumps({"profiles": [asdict(profile)]}), encoding="utf-8")
            env = {key: value for key, value in os.environ.items() if not key.startswith("BOT_BUDGET_") and key not in {"BOT_TOKEN", "SPREADSHEET_ID", "GOOGLE_CREDENTIALS_FILE"}}
            env["PYTHONUTF8"] = "1"
            code = "import sys; sys.path.insert(0,sys.argv[1]); from unittest.mock import patch; " + "\nwith patch('services.profile_secrets.load_token', return_value='222:protected_fake'):\n import config\n assert config.BOT_TOKEN == '222:protected_fake'\n assert config.SPREADSHEET_ID == 'managed-table'\n assert config.CURRENCY == 'RUB'\n assert config.GOOGLE_CREDENTIALS_FILE == 'own.json'\n assert config.PROFILE.legacy\n assert not config.PROFILE.uses_legacy_config"
            subprocess.run([sys.executable, "-B", "-c", code, str(base)], cwd=ROOT, env=env, capture_output=True, check=True)

    def test_restart_helper_explicitly_selects_current_profile(self):
        original = Path.exists
        with patch.object(Path, "exists", lambda path: False if path.name == ".env" else original(path)):
            from handlers import menu
        with patch.object(menu, "PROFILE_ID", "business"), patch.object(menu.subprocess, "Popen") as launch, patch.object(menu.os, "_exit"):
            asyncio.run(menu._restart_process_after_delay(0))
        helper = launch.call_args.args[0][2]
        calls = []
        fake_subprocess = type("Processes", (), {"run": staticmethod(lambda args, **kwargs: calls.append(args))})()
        fake_time = type("Clock", (), {"sleep": staticmethod(lambda seconds: None)})()
        with patch.dict(sys.modules, {"subprocess": fake_subprocess, "time": fake_time}):
            exec(compile(helper, "<restart-helper>", "exec"), {})
        self.assertEqual(calls[0][1:], ["manage_bot.py", "start", "--profile", "business"])

    def test_direct_secret_api_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            for invalid in ("../escape", "a/b", "a\\b", "", "C:drive"):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    profile_secrets.save_token(invalid, "123:fake", Path(directory))
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    profile_secrets.load_token(invalid, Path(directory))

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI")
    def test_real_dpapi_roundtrip_uses_generated_fake_token(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            fake_token = "123:fake_dpapi_token"
            profile_secrets.save_token("test", fake_token, base)
            self.assertNotIn(fake_token.encode("utf-8"), (base / ".profile-secrets" / "test.bin").read_bytes())
            self.assertEqual(profile_secrets.load_token("test", base), fake_token)


if __name__ == "__main__":
    unittest.main()
