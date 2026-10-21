"""Runtime flag selection from old and new profile registries, without secrets."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from services.bot_profiles import BotProfile, list_profiles


ROOT = Path(__file__).resolve().parents[1]


class MoneySourceProfileTests(unittest.TestCase):
    def test_old_json_defaults_off_and_selected_runtime_uses_own_flag(self):
        for setting in (None, False, True):
            with self.subTest(setting=setting), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                (base / "config.py").write_text((ROOT / "config.py").read_text(encoding="utf-8"), encoding="utf-8")
                profile = asdict(BotProfile("business", "Business", "business-sheet", "RUB"))
                if setting is None:
                    del profile["track_money_source"]
                else:
                    profile["track_money_source"] = setting
                (base / "profiles.json").write_text(json.dumps({"version": 1, "profiles": [profile]}), encoding="utf-8")
                self.assertIs(list_profiles(base)[0].track_money_source, bool(setting))
                env = {key: value for key, value in os.environ.items()
                       if not key.startswith("BOT_BUDGET_") and key not in {"BOT_TOKEN", "SPREADSHEET_ID", "GOOGLE_CREDENTIALS_FILE"}}
                env.update(BOT_BUDGET_PROFILE="business", PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
                program = """import sys,json
sys.path.insert(0,sys.argv[1])
from unittest.mock import patch
with patch('services.profile_secrets.load_token',return_value='123:fake'):
 import config
 print(json.dumps([config.PROFILE_ID,config.TRACK_MONEY_SOURCE]))
"""
                result = subprocess.run([sys.executable, "-c", program, str(base)], cwd=ROOT,
                                        env=env, capture_output=True, text=True, encoding="utf-8", check=True, timeout=15)
                self.assertEqual(json.loads(result.stdout), ["business", bool(setting)])


if __name__ == "__main__":
    unittest.main()
