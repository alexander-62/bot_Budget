import tempfile
import unittest
from pathlib import Path

import config
import secrets


class ConfigEnvTests(unittest.TestCase):
    def test_load_env_file_parses_common_dotenv_forms(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "# local config",
                        "BOT_TOKEN=token:123",
                        "SPREADSHEET_ID='sheet-id'",
                        'export GOOGLE_CREDENTIALS_FILE="credentials.json"',
                    ]
                ),
                encoding="utf-8",
            )

            values = config._load_env_file(env_path)

        self.assertEqual(values["BOT_TOKEN"], "token:123")
        self.assertEqual(values["SPREADSHEET_ID"], "sheet-id")
        self.assertEqual(values["GOOGLE_CREDENTIALS_FILE"], "credentials.json")

    def test_stdlib_secrets_module_is_available_after_config_import(self) -> None:
        self.assertTrue(callable(secrets.token_urlsafe))


if __name__ == "__main__":
    unittest.main()
