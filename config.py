from pathlib import Path

import secrets as app_secrets


def _require_secret_name(name: str) -> str:
    value = getattr(app_secrets, name, None)
    if value is None:
        raise RuntimeError(f"Missing required config name in secrets.py: {name}")
    if isinstance(value, str) and not value.strip():
        raise RuntimeError(f"Config name is empty in secrets.py: {name}")
    return str(value)


def _get_optional_setting(name: str, default):
    value = getattr(app_secrets, name, default)
    if isinstance(value, str):
        return value.strip()
    return value


BOT_TOKEN = _require_secret_name("BOT_TOKEN")
GOOGLE_CREDENTIALS_FILE = _require_secret_name("GOOGLE_CREDENTIALS_FILE")
SPREADSHEET_ID = _require_secret_name("SPREADSHEET_ID")
WEBAPP_URL = _get_optional_setting("WEBAPP_URL", "https://example.com/webapp")
WEBAPP_HOST = _get_optional_setting("WEBAPP_HOST", "127.0.0.1")
WEBAPP_PORT = int(_get_optional_setting("WEBAPP_PORT", 8080))


def get_credentials_path() -> Path:
    return Path(GOOGLE_CREDENTIALS_FILE).expanduser()
