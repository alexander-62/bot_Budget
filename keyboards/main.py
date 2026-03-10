from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from constants import (
    MENU_EXPENSES_TEXT,
    MENU_SHOPPING_TEXT,
    MENU_VIEW_EXPENSES_TEXT,
    MENU_VIEW_LIMITS_TEXT,
)


def build_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=f"📊 {MENU_VIEW_LIMITS_TEXT}"),
                KeyboardButton(text=f"🧾 {MENU_VIEW_EXPENSES_TEXT}"),
            ],
            [
                KeyboardButton(text=f"💸{MENU_EXPENSES_TEXT}"),
                KeyboardButton(text=f"🛒 {MENU_SHOPPING_TEXT}"),
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )
