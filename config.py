import importlib.util
import os
import sys
import sysconfig
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"


def _restore_stdlib_secrets_module() -> None:
    secrets_path = Path(sysconfig.get_paths()["stdlib"]) / "secrets.py"
    spec = importlib.util.spec_from_file_location("secrets", secrets_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load Python stdlib secrets module.")

    module = importlib.util.module_from_spec(spec)
    sys.modules["secrets"] = module
    spec.loader.exec_module(module)


_restore_stdlib_secrets_module()


def _unquote_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    return value


def _load_env_file(path: Path = ENV_FILE) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            raise RuntimeError(f"Invalid .env line {line_number}: expected NAME=value.")

        name, value = line.split("=", 1)
        name = name.strip()
        if not name:
            raise RuntimeError(f"Invalid .env line {line_number}: empty name.")
        values[name] = _unquote_env_value(value)

    return values


_ENV_VALUES = _load_env_file()


def _get_config_value(name: str, default: str = "") -> str:
    prefixed_value = os.getenv(f"BOT_BUDGET_{name}")
    if prefixed_value is not None and prefixed_value.strip():
        return prefixed_value.strip()

    env_value = os.getenv(name)
    if env_value is not None and env_value.strip():
        return env_value.strip()

    file_value = _ENV_VALUES.get(name)
    if file_value is not None and file_value.strip():
        return file_value.strip()

    return default


BOT_TOKEN = _get_config_value("BOT_TOKEN")
GOOGLE_CREDENTIALS_FILE = _get_config_value("GOOGLE_CREDENTIALS_FILE")
SPREADSHEET_ID = _get_config_value("SPREADSHEET_ID")
WEBAPP_HOST = _get_config_value("WEBAPP_HOST", "127.0.0.1")
WEBAPP_PORT = int(_get_config_value("WEBAPP_PORT", "8080"))
WEBAPP_URL = _get_config_value("WEBAPP_URL", f"http://{WEBAPP_HOST}:{WEBAPP_PORT}/webapp")


def get_credentials_path() -> Path:
    path = Path(GOOGLE_CREDENTIALS_FILE).expanduser()
    if path.is_absolute():
        return path
    return BASE_DIR / path
