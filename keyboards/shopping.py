from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_shopping_actions_keyboard(session_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Добавить", callback_data=f"sh:act:{session_id}:add", style="success"
                ),
                InlineKeyboardButton(
                    text="Убрать", callback_data=f"sh:act:{session_id}:remove", style="danger"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Очистить список",
                    callback_data=f"sh:act:{session_id}:clear",
                    style="danger",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Отмена", callback_data=f"sh:cancel:{session_id}", style="default"
                )
            ],
        ]
    )


def build_shopping_cancel_keyboard(session_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Отмена", callback_data=f"sh:cancel:{session_id}", style="default"
                )
            ]
        ]
    )


def build_shopping_clear_confirm_keyboard(session_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да", callback_data=f"sh:clear_yes:{session_id}", style="danger"
                ),
                InlineKeyboardButton(
                    text="Отмена", callback_data=f"sh:cancel:{session_id}", style="default"
                ),
            ]
        ]
    )
