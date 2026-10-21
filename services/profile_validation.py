"""User-triggered profile validation. Never expose transport errors or tokens."""
from dataclasses import dataclass
import json
from pathlib import Path
import re
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from config import BASE_DIR, get_credentials_path
from services.google_sheets import validate_profile_connection


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    message: str
    bot_id: int | None = None


def normalize_spreadsheet_id(value):
    value = value.strip()
    match = re.search(r"docs\.google\.com/spreadsheets/d/([A-Za-z0-9_-]+)", value)
    if match:
        return match.group(1)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Укажите ID таблицы или ссылку Google Sheets.")
    return value


def telegram_identity(token):
    # A transport exception may contain the URL including its token. Do not chain it.
    try:
        with urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=12) as response:
            payload = json.load(response)
        if not payload.get("ok") or not payload["result"].get("is_bot"):
            raise ValueError()
        return int(payload["result"]["id"])
    except Exception:
        raise ValueError("Telegram: проверьте токен BotFather и подключение к сети.") from None


def validate_profile(profile, token, *, profiles=(), token_loader=None,
                     check_telegram=telegram_identity, check_sheets=validate_profile_connection):
    try:
        if not profile.name.strip() or not re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", profile.id):
            raise ValueError()
        if profile.currency not in {"EUR", "RUB"}:
            raise ValueError()
        ZoneInfo(profile.timezone)
        normalize_spreadsheet_id(profile.spreadsheet_id)
    except Exception:
        return ValidationResult(False, "Проверьте название, ID профиля, валюту и часовой пояс (например Europe/Moscow).")
    if not token.strip():
        return ValidationResult(False, "Введите токен Telegram из BotFather.")
    try:
        bot_id = check_telegram(token.strip())
    except Exception:
        return ValidationResult(False, "Telegram: проверьте токен BotFather и подключение к сети.")
    for existing in profiles:
        if existing.id == profile.id:
            continue
        existing_spreadsheet = existing.spreadsheet_id
        if existing.legacy:
            import config
            existing_spreadsheet = config.SPREADSHEET_ID
        if existing_spreadsheet == profile.spreadsheet_id:
            return ValidationResult(False, "Эта таблица уже используется другим профилем. Выберите отдельную таблицу.")
        if token_loader:
            try:
                other = token_loader(existing)
                if other and int(other.split(":", 1)[0]) == bot_id:
                    return ValidationResult(False, "Этот Telegram-бот уже используется другим профилем.")
            except Exception:
                return ValidationResult(False, "Не удалось проверить токен другого профиля. Проверьте его настройки.")
    try:
        credentials = Path(profile.credentials_file) if profile.credentials_file else get_credentials_path()
        if not credentials.is_absolute():
            credentials = BASE_DIR / credentials
        check_sheets(profile, credentials)
    except ValueError as error:
        # Only schema messages created by our adapter are safe to display.
        message = str(error)
        if message.startswith(("Не найден лист «", "Лист «")) and token not in message:
            return ValidationResult(False, message)
        return ValidationResult(False, "Google Sheets: проверьте доступ сервисного аккаунта и структуру таблицы.")
    except Exception:
        return ValidationResult(False, "Google Sheets: проверьте файл ключа, доступ к таблице и подключение.")
    return ValidationResult(True, "Telegram и структура Google Sheets проверены.", bot_id)
