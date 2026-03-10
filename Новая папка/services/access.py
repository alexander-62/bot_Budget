import logging
import time

from aiogram import types

from constants import ACCESS_CACHE_TTL_SECONDS, USERS_SHEET_NAME
from services.google_sheets import (
    find_worksheet_case_insensitive,
    get_spreadsheet,
    normalize_username,
)

_allowed_usernames_cache: set[str] = set()
_allowed_usernames_cache_ts: float = 0.0

_allowed_chat_ids_cache: set[int] = set()
_allowed_chat_ids_cache_ts: float = 0.0

_allowed_user_chat_ids_cache: dict[str, int] = {}
_allowed_user_chat_ids_cache_ts: float = 0.0


def _load_allowed_usernames() -> set[str]:
    spreadsheet = get_spreadsheet()
    worksheet = find_worksheet_case_insensitive(spreadsheet, USERS_SHEET_NAME)
    raw_values = worksheet.col_values(1)

    allowed: set[str] = set()
    for value in raw_values:
        if not value.strip():
            continue
        normalized = normalize_username(value)
        if normalized in {"username", "usernames", "users"}:
            continue
        allowed.add(normalized)
    return allowed


def get_allowed_usernames() -> set[str]:
    global _allowed_usernames_cache, _allowed_usernames_cache_ts

    now = time.monotonic()
    if now - _allowed_usernames_cache_ts < ACCESS_CACHE_TTL_SECONDS and _allowed_usernames_cache:
        return _allowed_usernames_cache

    _allowed_usernames_cache = _load_allowed_usernames()
    _allowed_usernames_cache_ts = now
    return _allowed_usernames_cache


def _load_allowed_chat_ids() -> set[int]:
    spreadsheet = get_spreadsheet()
    worksheet = find_worksheet_case_insensitive(spreadsheet, USERS_SHEET_NAME)
    raw_values = worksheet.col_values(2)

    allowed_chat_ids: set[int] = set()
    for value in raw_values:
        raw = value.strip()
        if not raw:
            continue

        normalized = raw.lower()
        if normalized in {"user_id", "userid", "chat_id", "chatid", "id"}:
            continue

        try:
            allowed_chat_ids.add(int(raw))
        except ValueError:
            logging.warning("Некорректный chat_id/user_id в листе Users: %r", raw)
    return allowed_chat_ids


def get_allowed_chat_ids() -> set[int]:
    global _allowed_chat_ids_cache, _allowed_chat_ids_cache_ts

    now = time.monotonic()
    if now - _allowed_chat_ids_cache_ts < ACCESS_CACHE_TTL_SECONDS and _allowed_chat_ids_cache:
        return _allowed_chat_ids_cache

    _allowed_chat_ids_cache = _load_allowed_chat_ids()
    _allowed_chat_ids_cache_ts = now
    return _allowed_chat_ids_cache


def _load_allowed_user_chat_ids() -> dict[str, int]:
    spreadsheet = get_spreadsheet()
    worksheet = find_worksheet_case_insensitive(spreadsheet, USERS_SHEET_NAME)
    all_rows = worksheet.get_all_values()

    result: dict[str, int] = {}
    for row in all_rows:
        username_raw = row[0].strip() if len(row) > 0 else ""
        if not username_raw:
            continue

        normalized_username = normalize_username(username_raw)
        if normalized_username in {"username", "usernames", "users"}:
            continue

        chat_id_raw = row[1].strip() if len(row) > 1 else ""
        if not chat_id_raw:
            continue

        normalized_chat_id = chat_id_raw.lower()
        if normalized_chat_id in {"user_id", "userid", "chat_id", "chatid", "id"}:
            continue

        try:
            result[normalized_username] = int(chat_id_raw)
        except ValueError:
            logging.warning("Некорректный chat_id/user_id для @%s: %r", normalized_username, chat_id_raw)

    return result


def get_allowed_user_chat_ids() -> dict[str, int]:
    global _allowed_user_chat_ids_cache, _allowed_user_chat_ids_cache_ts

    now = time.monotonic()
    if now - _allowed_user_chat_ids_cache_ts < ACCESS_CACHE_TTL_SECONDS and _allowed_user_chat_ids_cache:
        return _allowed_user_chat_ids_cache

    _allowed_user_chat_ids_cache = _load_allowed_user_chat_ids()
    _allowed_user_chat_ids_cache_ts = now
    return _allowed_user_chat_ids_cache


def sync_allowed_user_chat_id(username: str | None, user_id: int | None) -> None:
    global _allowed_chat_ids_cache, _allowed_user_chat_ids_cache

    if not username or not user_id:
        return

    normalized_username = normalize_username(username)
    cached_user_chat_ids = get_allowed_user_chat_ids()
    cached_chat_id = cached_user_chat_ids.get(normalized_username)

    if cached_chat_id == user_id:
        return

    spreadsheet = get_spreadsheet()
    worksheet = find_worksheet_case_insensitive(spreadsheet, USERS_SHEET_NAME)
    usernames = worksheet.col_values(1)

    target_row: int | None = None
    for row_idx, username_raw in enumerate(usernames, start=1):
        if normalize_username(username_raw) == normalized_username:
            target_row = row_idx
            break

    if target_row is None:
        return

    worksheet.update_cell(target_row, 2, str(user_id))

    _allowed_chat_ids_cache.add(user_id)
    _allowed_user_chat_ids_cache[normalized_username] = user_id


def is_allowed_username(username: str | None) -> tuple[bool, str | None]:
    if not username:
        return False, "empty_username"

    normalized = normalize_username(username)
    if normalized not in get_allowed_usernames():
        return False, "username_not_found"
    return True, None


async def check_access_message(message: types.Message) -> bool:
    username = message.from_user.username if message.from_user else None
    user_id = message.from_user.id if message.from_user else None

    try:
        is_allowed, reason = is_allowed_username(username)
    except Exception:
        logging.exception("Не удалось загрузить список пользователей из Google Sheets")
        await message.answer("Ошибка проверки доступа. Попробуйте позже.")
        return False

    if is_allowed:
        try:
            sync_allowed_user_chat_id(username, user_id)
        except Exception:
            logging.exception("Не удалось синхронизировать chat_id/user_id для username=%s", username)
        return True

    if reason == "empty_username":
        await message.answer(
            "Доступ запрещен. У вас не установлен username в Telegram. "
            "Установите username и попросите добавить вас во вкладку Users."
        )
        return False

    await message.answer("Доступ запрещен. Ваш username не найден во вкладке Users.")
    return False


async def check_access_callback(callback: types.CallbackQuery) -> bool:
    username = callback.from_user.username if callback.from_user else None
    user_id = callback.from_user.id if callback.from_user else None

    try:
        is_allowed, reason = is_allowed_username(username)
    except Exception:
        logging.exception("Не удалось загрузить список пользователей из Google Sheets")
        await callback.answer("Ошибка проверки доступа. Попробуйте позже.", show_alert=True)
        return False

    if is_allowed:
        try:
            sync_allowed_user_chat_id(username, user_id)
        except Exception:
            logging.exception("Не удалось синхронизировать chat_id/user_id для username=%s", username)
        return True

    if reason == "empty_username":
        await callback.answer("Доступ запрещен. Установите username в Telegram.", show_alert=True)
        return False

    await callback.answer("Доступ запрещен.", show_alert=True)
    return False
