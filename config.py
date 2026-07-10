import importlib.util
import os
import sys
import sysconfig
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def _load_local_secrets():
    secrets_path = BASE_DIR / "secrets.py"
    spec = importlib.util.spec_from_file_location("_bot_budget_local_secrets", secrets_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load local secrets.py.")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _restore_stdlib_secrets_module() -> None:
    secrets_path = Path(sysconfig.get_paths()["stdlib"]) / "secrets.py"
    spec = importlib.util.spec_from_file_location("secrets", secrets_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load Python stdlib secrets module.")

    module = importlib.util.module_from_spec(spec)
    sys.modules["secrets"] = module
    spec.loader.exec_module(module)


app_secrets = _load_local_secrets()
_restore_stdlib_secrets_module()


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


def _get_runtime_override(name: str, default: str) -> str:
    value = os.getenv(f"BOT_BUDGET_{name}")
    if value is not None and value.strip():
        return value.strip()
    return default


BOT_TOKEN = _require_secret_name("BOT_TOKEN")
GOOGLE_CREDENTIALS_FILE = _require_secret_name("GOOGLE_CREDENTIALS_FILE")
SPREADSHEET_ID = _require_secret_name("SPREADSHEET_ID")
WEBAPP_HOST = _get_runtime_override("WEBAPP_HOST", _get_optional_setting("WEBAPP_HOST", "127.0.0.1"))
WEBAPP_PORT = int(_get_runtime_override("WEBAPP_PORT", str(_get_optional_setting("WEBAPP_PORT", 8080))))
WEBAPP_URL = _get_runtime_override(
    "WEBAPP_URL",
    _get_optional_setting("WEBAPP_URL", f"http://{WEBAPP_HOST}:{WEBAPP_PORT}/webapp"),
)


def get_credentials_path() -> Path:
    return Path(GOOGLE_CREDENTIALS_FILE).expanduser()
