"""User-triggered profile validation. Never expose transport errors or tokens."""
from dataclasses import dataclass
import json
from pathlib import Path
import re
from urllib.request import urlopen
from zoneinfo import ZoneInfo
from google.auth.exceptions import MalformedError, RefreshError, TransportError
from gspread.exceptions import APIError, SpreadsheetNotFound
from requests.exceptions import ConnectionError as RequestConnectionError, Timeout

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


def _sheets_error_message(error, token):
    """Only return app-authored diagnostics; transport text can contain secrets."""
    access_message = ("Google Sheets: нет доступа к таблице. В её настройках доступа добавьте "
                      "сервисный аккаунт общего ключа (или выбранного ключа) с правом «Редактор».")
    cause = error.__cause__
    api_error = error if isinstance(error, APIError) else cause if isinstance(cause, APIError) else None
    if isinstance(error, FileNotFoundError):
        return "Файл ключа Google не найден. Проверьте путь на этом компьютере или очистите поле для использования общего ключа."
    if isinstance(error, IsADirectoryError):
        return "Вместо файла ключа Google указана папка. Укажите JSON-файл ключа или настройте путь к общему ключу."
    if isinstance(error, PermissionError):
        if api_error is None:
            return "Нет прав на чтение файла ключа Google. Проверьте доступ к файлу на этом компьютере."
        # gspread wraps a Sheets HTTP 403 in PermissionError, retaining its cause.
    if isinstance(error, SpreadsheetNotFound):
        return "Таблица не найдена или недоступна. Проверьте ссылку/ID и выдайте сервисному аккаунту ключа доступ «Редактор»."
    if api_error is not None:
        details = api_error.error.get("details", [])
        if isinstance(details, list) and any(isinstance(detail, dict) and detail.get("reason") == "SERVICE_DISABLED" for detail in details):
            return "В проекте сервисного аккаунта включите Google Sheets API и Google Drive API, затем повторите проверку."
        if api_error.code == 403:
            return access_message
        if api_error.code == 401:
            return "Google не принял ключ. Укажите действующий JSON-ключ сервисного аккаунта."
        if api_error.code == 429:
            return "Превышен лимит запросов Google Sheets. Повторите проверку позже."
        if api_error.code >= 500:
            return "Google Sheets временно недоступен. Повторите проверку позже."
        return "Google Sheets отклонил запрос. Проверьте ссылку или ID таблицы и права сервисного аккаунта."
    if isinstance(error, (json.JSONDecodeError, UnicodeError, MalformedError)):
        return "Некорректный файл ключа Google. Выберите JSON-ключ сервисного аккаунта или используйте общий ключ."
    if isinstance(error, RefreshError):
        return "Google отклонил авторизацию ключа. Проверьте действующий ключ выбранного сервисного аккаунта."
    if isinstance(error, (TransportError, RequestConnectionError, Timeout, ConnectionError, TimeoutError)):
        return "Не удалось соединиться с Google. Проверьте интернет и повторите проверку."
    if isinstance(error, ValueError):
        message = str(error)
        if message.startswith(("Не найден лист «", "Лист «")) and token not in message:
            return message
        return "Google Sheets: проверьте файл ключа и структуру таблицы."
    return "Google Sheets: не удалось проверить подключение. Проверьте настройки ключа, доступ к таблице и интернет."


def validate_profile(profile, token, *, profiles=(), token_loader=None,
                     check_telegram=telegram_identity, check_sheets=validate_profile_connection):
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", profile.id):
        return ValidationResult(False, "ID профиля: от 1 до 48 символов, первая — строчная латинская буква. Далее допустимы строчные латинские буквы, цифры, дефис и подчёркивание. Например: st62.")
    try:
        if not profile.name.strip():
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
        if existing.uses_legacy_config:
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
    except Exception as error:
        return ValidationResult(False, _sheets_error_message(error, token))
    return ValidationResult(True, "Telegram и структура Google Sheets проверены.", bot_id)
