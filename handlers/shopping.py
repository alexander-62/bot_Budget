import logging
from html import escape

from aiogram import Router, types

from constants import MENU_SHOPPING_CALLBACK, MENU_SHOPPING_TEXT
from keyboards.shopping import (
    build_shopping_actions_keyboard,
    build_shopping_cancel_keyboard,
    build_shopping_clear_confirm_keyboard,
)
from services.async_tools import run_blocking
from services.access import check_access_callback, check_access_message
from services.shopping import (
    add_shopping_items,
    clear_shopping_list,
    get_shopping_items,
    remove_shopping_items_by_numbers,
    remove_shopping_item_by_number,
)
from services.settings_middleware import abandon_sessions
from state.dialog_messages import close_dialog, dialog_hint, dialog_result, dialog_step
from state.shopping_session import (
    create_session,
    get_active_session,
    is_stale_session,
    pop_session,
    touch_session,
)

router = Router()


def _format_shopping_list(items: list[str]) -> str:
    if not items:
        return "Список покупок пуст"
    lines = ["Список покупок:"]
    for idx, item in enumerate(items, start=1):
        lines.append(f"{idx}. {escape(item)}")
    return "\n".join(lines)


async def _show_shopping_list(message: types.Message, user_id: int) -> None:
    pop_session(user_id)
    try:
        items = await run_blocking(get_shopping_items)
    except Exception:
        logging.exception("Ошибка чтения списка покупок")
        await dialog_step(message, "Не удалось обновить список покупок. Попробуйте позже.")
        return

    session = create_session(user_id=user_id, state="menu")
    await dialog_step(
        message, _format_shopping_list(items),
        reply_markup=build_shopping_actions_keyboard(session.session_id),
    )


async def _cancel_shopping_flow(user_id: int) -> None:
    pop_session(user_id)
    await close_dialog()


@router.message(
    lambda message: bool(message.text) and message.text.endswith(MENU_SHOPPING_TEXT)
)
async def start_shopping_flow(message: types.Message) -> None:
    if not await check_access_message(message):
        return
    user_id = message.from_user.id if message.from_user else 0
    await _show_shopping_list(message, user_id)


@router.callback_query(lambda c: c.data == MENU_SHOPPING_CALLBACK)
async def start_shopping_flow_callback(callback: types.CallbackQuery) -> None:
    if not await check_access_callback(callback):
        return
    if not isinstance(callback.message, types.Message):
        await callback.answer("Ошибка сообщения.", show_alert=True)
        return
    await callback.answer()
    user_id = callback.from_user.id
    abandon_sessions(user_id)
    await _show_shopping_list(callback.message, user_id)


@router.message(lambda message: bool(message.from_user and get_active_session(message.from_user.id)))
async def shopping_text_step(message: types.Message) -> None:
    if not await check_access_message(message):
        return
    if not message.text:
        return

    user_id = message.from_user.id if message.from_user else 0
    session = get_active_session(user_id)
    if session is None:
        return
    if message.text.strip().lower() in {"отмена", "/cancel"}:
        await _cancel_shopping_flow(user_id)
        return
    touch_session(session)

    if session.state == "await_add_text":
        try:
            raw_items = [part.strip() for part in message.text.split(",")]
            items_to_add = [item for item in raw_items if item]
            if not items_to_add:
                raise ValueError("Пустой ввод не допускается")

            added_items, existing_items = await run_blocking(add_shopping_items, items_to_add)
            for item in added_items:
                logging.info(
                    "shopping_add user_id=%s username=%s item=%s status=success",
                    user_id,
                    message.from_user.username if message.from_user else None,
                    item,
                )
            for item in existing_items:
                logging.info(
                    "shopping_add user_id=%s username=%s item=%s status=deduplicated",
                    user_id,
                    message.from_user.username if message.from_user else None,
                    item,
                )

            summary = []
            if added_items:
                summary.append(f"Добавлено ({len(added_items)}): {escape(', '.join(added_items))}")
            if existing_items:
                summary.append(f"Уже в списке ({len(existing_items)}): {escape(', '.join(existing_items))}")
        except ValueError as exc:
            await dialog_hint(message, escape(str(exc)))
            return
        except Exception:
            logging.exception("Ошибка добавления позиции в список покупок")
            await dialog_hint(message, "Не удалось обновить список покупок. Попробуйте позже.")
            return

        if summary:
            await dialog_result(message, "\n".join(summary))
        await _show_shopping_list(message, user_id)
        return

    if session.state == "await_remove_number":
        raw_numbers = [part.strip() for part in message.text.split(",")]
        number_tokens = [token for token in raw_numbers if token]
        if not number_tokens or not all(token.isdigit() for token in number_tokens):
            await dialog_hint(message, "Неверный номер, попробуйте снова")
            return

        try:
            numbers = [int(token) for token in number_tokens]
            if len(numbers) == 1:
                removed_item = await run_blocking(remove_shopping_item_by_number, numbers[0])
                logging.info(
                    "shopping_remove user_id=%s username=%s numbers=%s items=%s status=success",
                    user_id,
                    message.from_user.username if message.from_user else None,
                    ",".join(number_tokens),
                    removed_item,
                )
                summary = f"Удалено: {escape(removed_item)}"
            else:
                removed_items = await run_blocking(remove_shopping_items_by_numbers, numbers)
                logging.info(
                    "shopping_remove user_id=%s username=%s numbers=%s items=%s status=success",
                    user_id,
                    message.from_user.username if message.from_user else None,
                    ",".join(number_tokens),
                    ",".join(removed_items),
                )
                summary = f"Удалено ({len(removed_items)}): {escape(', '.join(removed_items))}"
        except ValueError:
            await dialog_hint(message, "Неверный номер, попробуйте снова")
            return
        except Exception:
            logging.exception("Ошибка удаления позиции из списка покупок")
            await dialog_hint(message, "Не удалось обновить список покупок. Попробуйте позже.")
            return

        await dialog_result(message, summary)
        await _show_shopping_list(message, user_id)
        return

    await dialog_hint(message, "Используйте кнопки текущего шага или отправьте /cancel.")


@router.callback_query(lambda c: c.data and c.data.startswith("sh:cancel:"))
async def shopping_cancel_handler(callback: types.CallbackQuery) -> None:
    if not await check_access_callback(callback):
        return
    user_id = callback.from_user.id
    session_id = callback.data.split(":")[2]
    if is_stale_session(user_id, session_id):
        await callback.answer("Шаг устарел, начните заново", show_alert=True)
        return
    await _cancel_shopping_flow(user_id)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("sh:act:"))
async def shopping_action_handler(callback: types.CallbackQuery) -> None:
    if not await check_access_callback(callback):
        return
    if not isinstance(callback.message, types.Message):
        await callback.answer("Ошибка сообщения.", show_alert=True)
        return

    user_id = callback.from_user.id
    _, _, session_id, action = callback.data.split(":", 3)
    if is_stale_session(user_id, session_id):
        await callback.answer("Шаг устарел, начните заново", show_alert=True)
        return

    session = get_active_session(user_id)
    if session is None or session.state != "menu":
        await callback.answer("Шаг устарел, начните заново", show_alert=True)
        return

    if action == "add":
        session.state = "await_add_text"
        touch_session(session)
        await dialog_step(
            callback.message,
            "Введите позицию для списка покупок. Можно добавить несколько через запятую.",
            reply_markup=build_shopping_cancel_keyboard(session.session_id),
        )
        touch_session(session)
        await callback.answer()
        return

    if action == "remove":
        try:
            items = await run_blocking(get_shopping_items)
        except Exception:
            logging.exception("Ошибка чтения списка покупок")
            await callback.answer("Не удалось обновить список покупок. Попробуйте позже.", show_alert=True)
            return

        if not items:
            await callback.answer("Список пуст, удалять нечего", show_alert=True)
            return

        session.state = "await_remove_number"
        touch_session(session)
        lines = ["Введите номер позиции для удаления:"]
        lines.append("Можно указать несколько номеров через запятую.")
        for idx, item in enumerate(items, start=1):
            lines.append(f"{idx}. {escape(item)}")
        await dialog_step(
            callback.message,
            "\n".join(lines),
            reply_markup=build_shopping_cancel_keyboard(session.session_id),
        )
        touch_session(session)
        await callback.answer()
        return

    if action == "clear":
        session.state = "await_clear_confirm"
        touch_session(session)
        await dialog_step(
            callback.message,
            "Очистить весь список покупок?",
            reply_markup=build_shopping_clear_confirm_keyboard(session.session_id),
        )
        touch_session(session)
        await callback.answer()
        return

    await callback.answer("Неизвестное действие", show_alert=True)


@router.callback_query(lambda c: c.data and c.data.startswith("sh:clear_yes:"))
async def shopping_clear_yes_handler(callback: types.CallbackQuery) -> None:
    if not await check_access_callback(callback):
        return

    user_id = callback.from_user.id
    session_id = callback.data.split(":")[2]
    if is_stale_session(user_id, session_id):
        await callback.answer("Шаг устарел, начните заново", show_alert=True)
        return

    session = get_active_session(user_id)
    if session is None or session.state != "await_clear_confirm":
        await callback.answer("Шаг устарел, начните заново", show_alert=True)
        return

    try:
        await run_blocking(clear_shopping_list)
        logging.info(
            "shopping_clear user_id=%s username=%s status=success",
            user_id,
            callback.from_user.username if callback.from_user else None,
        )
    except Exception:
        logging.exception("Ошибка очистки списка покупок")
        await callback.answer("Не удалось обновить список покупок. Попробуйте позже.", show_alert=True)
        return

    await callback.answer()
    if isinstance(callback.message, types.Message):
        await dialog_result(callback.message, "Список покупок очищен")
        await _show_shopping_list(callback.message, user_id)
