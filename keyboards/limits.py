from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from constants import MENU_EXPENSES_CALLBACK


def build_categories_keyboard(categories: list[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for idx, category in enumerate(categories):
        rows.append(
            [
                InlineKeyboardButton(
                    text=category,
                    callback_data=f"viewcat:{idx}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_category_actions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💸Добавить трату",
                    callback_data=MENU_EXPENSES_CALLBACK,
                )
            ]
        ]
    )
