from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo

from config import WEBAPP_URL
from constants import (
    MENU_EXPENSES_TEXT,
    MENU_SHOPPING_TEXT,
    MENU_VIEW_EXPENSES_TEXT,
    MENU_VIEW_LIMITS_TEXT,
    MENU_WEBAPP_TEXT,
)


def build_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=f"📊 {MENU_VIEW_LIMITS_TEXT}"),
                KeyboardButton(text=f"🧾 {MENU_VIEW_EXPENSES_TEXT}"),
            ],
            [
                KeyboardButton(text=f"💸 {MENU_EXPENSES_TEXT}"),
                KeyboardButton(text=f"🛒 {MENU_SHOPPING_TEXT}"),
            ],
            [
                KeyboardButton(
                    text=f"🌐 {MENU_WEBAPP_TEXT}",
                    web_app=WebAppInfo(url=WEBAPP_URL),
                ),
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )
