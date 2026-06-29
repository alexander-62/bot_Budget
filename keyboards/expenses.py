from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_cancel_keyboard(session_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Отмена", callback_data=f"exp:cancel:{session_id}"
                )
            ]
        ]
    )


def build_expense_categories_keyboard(
    categories: list[str], session_id: str
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for idx, category in enumerate(categories):
        rows.append(
            [
                InlineKeyboardButton(
                    text=category,
                    callback_data=f"exp:cat:{session_id}:{idx}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(text="Отмена", callback_data=f"exp:cancel:{session_id}")
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_expense_subcategories_keyboard(
    subcategories: list[str], session_id: str
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for idx, subcategory in enumerate(subcategories):
        rows.append(
            [
                InlineKeyboardButton(
                    text=subcategory,
                    callback_data=f"exp:sub:{session_id}:{idx}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(text="Отмена", callback_data=f"exp:cancel:{session_id}")
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_confirm_keyboard(session_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Сохранить", callback_data=f"exp:yes:{session_id}"
                ),
                InlineKeyboardButton(text="Отмена", callback_data=f"exp:cancel:{session_id}"),
            ]
        ]
    )


def build_saved_expense_actions_keyboard(action_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Изменить", callback_data=f"exp:saved:edit:{action_id}")],
            [InlineKeyboardButton(text="Добавить ещё в эту категорию", callback_data=f"exp:saved:repeat:{action_id}")],
            [InlineKeyboardButton(text="Добавить другую трату", callback_data=f"exp:saved:fresh:{action_id}")],
        ]
    )


def build_saved_expense_edit_keyboard(action_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Удалить", callback_data=f"exp:saved:delete:{action_id}")],
            [InlineKeyboardButton(text="Отмена", callback_data=f"exp:saved:cancel:{action_id}")],
        ]
    )
