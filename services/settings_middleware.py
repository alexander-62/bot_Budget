"""Refresh shared budget preferences off the event loop before rendering updates."""
import logging
from aiogram import BaseMiddleware
from services.async_tools import run_blocking
from services.budget_settings import settings_initialized, refresh_runtime_settings


class BudgetSettingsMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if settings_initialized():
            try:
                await run_blocking(refresh_runtime_settings)
            except Exception:
                logging.exception("Не удалось прочитать настройки бюджета")
                await event.answer("Не удалось загрузить настройки бюджета. Проверьте лист «Настройки» и повторите попытку.")
                return
        # Menu navigation abandons any unfinished flow before router filters run.
        from constants import MENU_EXPENSES_TEXT, MENU_SHOPPING_TEXT, MENU_VIEW_EXPENSES_TEXT, MENU_VIEW_LIMITS_TEXT, MENU_WEBAPP_TEXT
        text = getattr(event, "text", None)
        callback = getattr(event, "data", None)
        navigation = text in {"/start", "/settings", "Настройки", "⚙️ Настройки"} or (
            isinstance(text, str) and any(text.endswith(label) for label in
            (MENU_EXPENSES_TEXT, MENU_SHOPPING_TEXT, MENU_VIEW_EXPENSES_TEXT, MENU_VIEW_LIMITS_TEXT, MENU_WEBAPP_TEXT, "Расходы за месяц")))
        if navigation or (isinstance(callback, str) and callback.startswith("main:")):
            user = getattr(event, "from_user", None)
            if user:
                from state.settings_session import pop_session
                from state.expense_session import pop_session as pop_expense
                from state.shopping_session import pop_session as pop_shopping
                pop_session(user.id)
                pop_expense(user.id)
                pop_shopping(user.id)
        return await handler(event, data)
