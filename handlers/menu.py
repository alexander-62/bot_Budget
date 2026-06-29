import asyncio
import json
import logging
import os
import subprocess
import sys
from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from aiogram import Router, types
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder

from constants import MENU_LIMITS_CALLBACK, MENU_VIEW_EXPENSES_TEXT, MENU_VIEW_LIMITS_TEXT
from keyboards.limits import build_categories_keyboard, build_category_actions_keyboard
from keyboards.main import build_main_menu
from services.async_tools import run_blocking
from services.access import check_access_callback, check_access_message
from services.budget import get_budget_limits, get_category_details, get_month_totals
from services.expenses import get_recent_expenses
from services.google_sheets import get_spreadsheet_url
from version import __version__

BASE_DIR = Path(__file__).resolve().parents[1]
RESTART_NOTICE_FILE = BASE_DIR / ".restart_notice.json"

router = Router()
_restart_in_progress = False


@dataclass(frozen=True)
class GitPullResult:
    ok: bool
    before_sha: str = ""
    after_sha: str = ""
    user_message: str = ""
    log_message: str = ""


def _parse_sheet_number(value: str) -> Decimal:
    normalized = value.replace("\xa0", "").replace(" ", "").replace("€", "").replace(",", ".")
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(f"Некорректное число: {value}") from exc


def _format_eur_rounded(value: str) -> str:
    rounded = _parse_sheet_number(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{int(rounded):,}".replace(",", " ")


def _format_money_or_dash(value: str) -> str:
    value = value.strip()
    if not value or value == "—" or value == "не указан":
        return "—"
    return f"{_format_eur_rounded(value)} €"


def _format_remaining_with_alert(value: str) -> str:
    value = value.strip()
    if not value or value == "—" or value == "не указан":
        return "—"

    dec_value = _parse_sheet_number(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    formatted = f"{int(dec_value):,}".replace(",", " ") + " €"
    if dec_value < 0:
        return f"{formatted} ⚠️"
    return formatted


def _write_restart_notice(chat_id: int, username: str | None) -> None:
    RESTART_NOTICE_FILE.write_text(
        json.dumps(
            {
                "chat_id": chat_id,
                "username": username,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


async def _send_limits(target_message: types.Message) -> None:
    try:
        total_limit, categories = await run_blocking(get_budget_limits)
        month_limit, month_spent, month_remaining = await run_blocking(get_month_totals)
    except Exception:
        logging.exception("Ошибка чтения лимитов из Google Sheets")
        await target_message.answer("Не удалось загрузить лимиты. Попробуйте позже.")
        return

    if not categories:
        await target_message.answer("Категории не найдены в таблице.")
        return

    try:
        limit_fmt = _format_eur_rounded(month_limit or total_limit)
        spent_fmt = _format_eur_rounded(month_spent)
        remaining_fmt = _format_eur_rounded(month_remaining)
    except Exception:
        logging.exception("Ошибка форматирования значений лимитов")
        await target_message.answer("Не удалось загрузить лимиты. Попробуйте позже.")
        return

    today = date.today()
    days_left = monthrange(today.year, today.month)[1] - today.day

    text = (
        "📌 Лимит:\n"
        f"<b>{limit_fmt} €</b>\n\n"
        "💸 Потрачено:\n"
        f"<b>{spent_fmt} €</b>\n\n"
        "💰 Осталось:\n"
        f"<b>{remaining_fmt} €</b>\n\n"
        "📅 Дней до конца месяца:\n"
        f"<b>{days_left}</b>"
    )
    await target_message.answer(text, reply_markup=build_categories_keyboard(categories))


async def _send_recent_expenses(target_message: types.Message, limit: int = 5) -> None:
    try:
        recent = await run_blocking(get_recent_expenses, limit)
    except Exception:
        logging.exception("Ошибка чтения последних трат из Google Sheets")
        await target_message.answer("Не удалось загрузить траты. Попробуйте позже.")
        return

    if not recent:
        await target_message.answer("Траты не найдены.")
        return

    lines = [f"Последние {len(recent)} трат:"]
    for idx, (date_value, username_value, category_value, subcategory_value, amount_value, comment_value) in enumerate(
        recent,
        start=1,
    ):
        lines.append(f"{idx}. <b>{date_value}</b> | <b>{amount_value}</b> | <b>{subcategory_value}</b>")
        details = [f"Пользователь: {username_value}"]
        if category_value:
            details.append(f"Категория: {category_value}")
        lines.append(" | ".join(details))
        if comment_value:
            lines.append(f"Комментарий: {comment_value}")
        lines.append("")

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Открыть гугл таблицу", url=get_spreadsheet_url())
    await target_message.answer(
        "\n".join(lines).strip(),
        reply_markup=keyboard.as_markup(),
    )


async def _restart_process_after_delay(delay_seconds: int = 5) -> None:
    helper_code = (
        "import subprocess, sys, time\n"
        f"time.sleep({delay_seconds})\n"
        f"subprocess.run([sys.executable, 'manage_bot.py', 'start'], cwd={json.dumps(str(BASE_DIR))}, check=False)\n"
    )
    kwargs = {
        "cwd": str(BASE_DIR),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        creationflags = 0
        creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
        creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        if creationflags:
            kwargs["creationflags"] = creationflags

    try:
        subprocess.Popen([sys.executable, "-c", helper_code], **kwargs)
    except Exception:
        logging.exception("Не удалось запустить helper для перезапуска")
        return

    os._exit(0)


def _run_git_pull() -> tuple[bool, str, str]:
    git_check = subprocess.run(
        ["git", "--version"],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if git_check.returncode != 0:
        return GitPullResult(
            ok=False,
            user_message="Не удалось обновиться: Git не найден на машине.",
            log_message=(git_check.stderr or git_check.stdout).strip(),
        )

    fetch = subprocess.run(
        ["git", "fetch", "origin", "main"],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if fetch.returncode != 0:
        return GitPullResult(
            ok=False,
            user_message="Не удалось обновиться: не удалось получить обновления из GitHub.",
            log_message=(fetch.stderr or fetch.stdout).strip(),
        )

    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if branch.returncode != 0:
        return GitPullResult(
            ok=False,
            user_message="Не удалось обновиться: не удалось определить текущую ветку Git.",
            log_message=(branch.stderr or branch.stdout).strip(),
        )

    current_branch = branch.stdout.strip()
    if current_branch.lower() != "main":
        switch = subprocess.run(
            ["git", "switch", "main"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if switch.returncode != 0:
            create_main = subprocess.run(
                ["git", "switch", "-c", "main", "--track", "origin/main"],
                cwd=BASE_DIR,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if create_main.returncode != 0:
                return GitPullResult(
                    ok=False,
                    user_message="Не удалось обновиться: не получилось создать локальную ветку main.",
                    log_message=(create_main.stderr or create_main.stdout).strip(),
                )
        current_branch = "main"

    before = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if before.returncode != 0:
        return GitPullResult(
            ok=False,
            user_message="Не удалось обновиться: не удалось прочитать текущий commit.",
            log_message=before.stderr.strip() or before.stdout.strip(),
        )

    pull = subprocess.run(
        ["git", "pull", "--ff-only", "origin", "main"],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if pull.returncode != 0:
        message = (pull.stderr or pull.stdout).strip()
        lowered = message.lower()
        if "not possible to fast-forward" in lowered or "fast-forward" in lowered:
            user_message = "Не удалось обновиться: локальная ветка main не fast-forward к origin/main."
        elif "local changes" in lowered or "would be overwritten" in lowered:
            user_message = "Не удалось обновиться: есть локальные изменения в репозитории."
        elif "could not resolve host" in lowered or "failed to connect" in lowered:
            user_message = "Не удалось обновиться: нет соединения с GitHub."
        else:
            user_message = "Не удалось обновиться: git pull завершился ошибкой."
        return GitPullResult(
            ok=False,
            user_message=user_message,
            log_message=message,
        )

    after = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if after.returncode != 0:
        return GitPullResult(
            ok=False,
            user_message="Обновление скачано, но не удалось прочитать новый commit.",
            log_message=after.stderr.strip() or after.stdout.strip(),
        )

    return GitPullResult(
        ok=True,
        before_sha=before.stdout.strip(),
        after_sha=after.stdout.strip(),
    )


@router.message(CommandStart())
async def cmd_start(message: types.Message) -> None:
    if not await check_access_message(message):
        return
    await message.answer("Привет! Выберите действие из меню.", reply_markup=build_main_menu())


@router.message(
    lambda message: bool(message.text) and message.text.endswith(MENU_VIEW_LIMITS_TEXT)
)
async def view_limits_handler(message: types.Message) -> None:
    if not await check_access_message(message):
        return
    await _send_limits(message)


@router.message(
    lambda message: bool(message.text) and message.text.endswith(MENU_VIEW_EXPENSES_TEXT)
)
async def view_recent_expenses_handler(message: types.Message) -> None:
    if not await check_access_message(message):
        return
    await _send_recent_expenses(message, limit=5)


@router.message(lambda message: bool(message.text) and message.text.strip().lower() == "перезапуск")
async def restart_handler(message: types.Message) -> None:
    global _restart_in_progress

    if not await check_access_message(message):
        return

    if _restart_in_progress:
        await message.answer("Перезапуск уже запущен. Подождите несколько секунд.")
        return

    _restart_in_progress = True
    logging.warning("Запрошен удаленный перезапуск бота пользователем @%s", message.from_user.username if message.from_user else "unknown")
    try:
        _write_restart_notice(
            chat_id=message.chat.id,
            username=message.from_user.username if message.from_user else None,
        )
    except Exception:
        logging.exception("Не удалось записать marker перезапуска")
        _restart_in_progress = False
        await message.answer("Не удалось подготовить перезапуск. Попробуйте позже.")
        return
    await message.answer("Проверяю обновления...")

    try:
        pull_result = await asyncio.to_thread(_run_git_pull)
    except Exception:
        logging.exception("Ошибка обновления из GitHub")
        _restart_in_progress = False
        await message.answer("Не удалось обновиться. Попробуйте позже.")
        return

    if not pull_result.ok:
        _restart_in_progress = False
        logging.warning("Удаленный перезапуск: обновление не выполнено: %s", pull_result.log_message)
        await message.answer(pull_result.user_message or "Не удалось обновиться. Попробуйте позже.")
        return

    if pull_result.before_sha == pull_result.after_sha:
        await message.answer(f"Обновление не найдено. Перезапускаюсь. Версия: {__version__}")
    else:
        await message.answer(f"Обновление установлено. Перезапускаюсь. Версия: {__version__}")
    asyncio.create_task(_restart_process_after_delay(5))


@router.callback_query(lambda c: c.data == MENU_LIMITS_CALLBACK)
async def view_limits_from_main_menu(callback: types.CallbackQuery) -> None:
    if not await check_access_callback(callback):
        return
    await callback.answer()
    if callback.message:
        await _send_limits(callback.message)


@router.callback_query(lambda c: c.data and c.data.startswith("viewcat:"))
async def category_click_handler(callback: types.CallbackQuery) -> None:
    if not await check_access_callback(callback):
        return

    category_idx_raw = callback.data.split(":", 1)[1]
    if not category_idx_raw.isdigit():
        await callback.answer("Некорректная категория.", show_alert=True)
        return

    category_idx = int(category_idx_raw)

    try:
        _, categories = await run_blocking(get_budget_limits)
        if category_idx < 0 or category_idx >= len(categories):
            await callback.answer("Категория больше не актуальна. Обновите меню.", show_alert=True)
            return

        category_name = categories[category_idx]
        (
            category_title,
            category_limit,
            category_spent,
            category_remaining,
            subcategories,
        ) = await run_blocking(get_category_details, category_name)
    except Exception:
        logging.exception("Ошибка чтения категории из Google Sheets")
        await callback.answer("Не удалось загрузить категорию.", show_alert=True)
        return

    category_limit_fmt = _format_money_or_dash(category_limit)
    category_spent_fmt = _format_money_or_dash(category_spent)
    category_remaining_fmt = _format_remaining_with_alert(category_remaining)

    lines = [
        f"🏷️ <b>{category_title}</b>",
        "📊 Лимит / Потрачено / Осталось",
        f"<b>{category_limit_fmt} / {category_spent_fmt} / {category_remaining_fmt}</b>",
        "",
        "🧾 Подкатегории:",
    ]
    if subcategories:
        for sub_name, sub_limit, sub_spent, sub_remaining in subcategories:
            sub_limit_fmt = _format_money_or_dash(sub_limit)
            sub_spent_fmt = _format_money_or_dash(sub_spent)
            sub_remaining_fmt = _format_remaining_with_alert(sub_remaining)
            lines.append(f"👉<b>{sub_name}</b>")
            lines.append("Лимит / Потрачено / Осталось")
            lines.append(f"<b>{sub_limit_fmt} / {sub_spent_fmt} / {sub_remaining_fmt}</b>")
            lines.append("")
    else:
        lines.append("- нет подкатегорий")

    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "\n".join(lines).strip(),
            reply_markup=build_category_actions_keyboard(),
        )


@router.message()
async def fallback_handler(message: types.Message) -> None:
    if not await check_access_message(message):
        return
    await message.answer("Выберите действие из меню.", reply_markup=build_main_menu())
