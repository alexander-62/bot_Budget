"""Refresh budget settings and release previous sessions on menu navigation."""
import logging

from aiogram import BaseMiddleware, types

from constants import (
    MENU_EXPENSES_TEXT, MENU_PLANNED_TEXT, MENU_SHOPPING_TEXT,
    MENU_VIEW_EXPENSES_TEXT, MENU_VIEW_LIMITS_TEXT, MENU_WEBAPP_TEXT,
)
from services.async_tools import run_blocking
from services.budget_settings import settings_initialized, refresh_runtime_settings
from state.dialog_messages import close_dialog, dialog_hint
from state.expense_session import pop_session as pop_expense
from state.planned_session import pop_session as pop_planned
from state.saved_expense_actions import finalize_saved_expense_action
from state.settings_session import pop_session as pop_settings
from state.shopping_session import pop_session as pop_shopping


def abandon_sessions(user_id):
    pop_settings(user_id)
    pop_expense(user_id)
    pop_shopping(user_id)
    pop_planned(user_id)
    finalize_saved_expense_action(user_id)


def _is_menu_navigation(text):
    if not text:
        return False
    command = text.split(maxsplit=1)[0].split("@", 1)[0] if text.startswith("/") else ""
    return (
        command == "/start"
        or text in {"/settings", "/planned", MENU_PLANNED_TEXT, f"📅 {MENU_PLANNED_TEXT}", "Настройки", "⚙️ Настройки"}
        or text.strip().lower() in {"лог", "перезапуск"}
        or text.endswith((
            MENU_EXPENSES_TEXT, MENU_SHOPPING_TEXT, MENU_VIEW_EXPENSES_TEXT,
            MENU_VIEW_LIMITS_TEXT, MENU_WEBAPP_TEXT, "Расходы за месяц",
        ))
    )


class BudgetSettingsMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if settings_initialized():
            try:
                await run_blocking(refresh_runtime_settings)
            except Exception:
                logging.exception("Не удалось прочитать настройки бюджета")
                text = "Не удалось загрузить настройки бюджета. Проверьте лист «Настройки» и повторите попытку."
                if isinstance(event, types.CallbackQuery):
                    await event.answer(text, show_alert=True)
                else:
                    await dialog_hint(event, text)
                return
        if isinstance(event, types.Message) and event.from_user and _is_menu_navigation(event.text):
            abandon_sessions(event.from_user.id)
            await close_dialog()
        return await handler(event, data)
