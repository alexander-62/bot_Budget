import logging

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
        lines.append(f"{idx}. {item}")
    return "\n".join(lines)


async def _safe_delete_prompt(bot, chat_id: int | None, message_id: int | None) -> None:
    if chat_id is None or message_id is None:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        logging.exception("Не удалось удалить сообщение шага (shopping)")


async def _safe_delete_session_messages(bot, session) -> None:
    await _safe_delete_prompt(bot, session.step_chat_id, session.step_message_id)
    await _safe_delete_prompt(bot, session.list_chat_id, session.list_message_id)


async def _show_shopping_list(message: types.Message, user_id: int) -> None:
    session_old = pop_session(user_id)
    if session_old:
        await _safe_delete_session_messages(message.bot, session_old)

    try:
        items = await run_blocking(get_shopping_items)
    except Exception:
        logging.exception("Ошибка чтения списка покупок")
        await message.answer("Не удалось обновить список покупок. Попробуйте позже.")
        return

    session = create_session(user_id=user_id, state="menu")
    prompt = await message.answer(
        _format_shopping_list(items),
        reply_markup=build_shopping_actions_keyboard(session.session_id),
    )
    session.list_chat_id = prompt.chat.id
    session.list_message_id = prompt.message_id


async def _show_shopping_list_callback(callback: types.CallbackQuery, user_id: int) -> None:
    session_old = pop_session(user_id)
    if session_old:
        await _safe_delete_session_messages(callback.bot, session_old)

    try:
        items = await run_blocking(get_shopping_items)
    except Exception:
        logging.exception("Ошибка чтения списка покупок")
        await callback.answer("Не удалось обновить список покупок. Попробуйте позже.", show_alert=True)
        return

    session = create_session(user_id=user_id, state="menu")
    if callback.message is None:
        await callback.answer("Ошибка сообщения.", show_alert=True)
        return
    prompt = await callback.message.answer(
        _format_shopping_list(items),
        reply_markup=build_shopping_actions_keyboard(session.session_id),
    )
    session.list_chat_id = prompt.chat.id
    session.list_message_id = prompt.message_id


async def _cancel_shopping_flow(user_id: int, notify_target: types.Message | types.CallbackQuery) -> None:
    session = pop_session(user_id)
    if session:
        await _safe_delete_session_messages(notify_target.bot, session)

    if isinstance(notify_target, types.CallbackQuery):
        await notify_target.answer()
        return

    await notify_target.answer()


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
    if callback.message is None:
        await callback.answer("Ошибка сообщения.", show_alert=True)
        return
    await callback.answer()
    user_id = callback.from_user.id if callback.from_user else 0
    await _show_shopping_list_callback(callback, user_id)


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

            if added_items:
                await message.answer(f"Добавлено ({len(added_items)}): {', '.join(added_items)}")
            if existing_items:
                await message.answer(f"Уже в списке ({len(existing_items)}): {', '.join(existing_items)}")
        except ValueError as exc:
            await message.answer(
                str(exc),
                reply_markup=build_shopping_cancel_keyboard(session.session_id),
            )
            return
        except Exception:
            logging.exception("Ошибка добавления позиции в список покупок")
            await message.answer("Не удалось обновить список покупок. Попробуйте позже.")
            return

        await _show_shopping_list(message, user_id)
        return

    if session.state == "await_remove_number":
        raw_numbers = [part.strip() for part in message.text.split(",")]
        number_tokens = [token for token in raw_numbers if token]
        if not number_tokens or not all(token.isdigit() for token in number_tokens):
            await message.answer(
                "Неверный номер, попробуйте снова",
                reply_markup=build_shopping_cancel_keyboard(session.session_id),
            )
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
                await message.answer(f"Удалено: {removed_item}")
            else:
                removed_items = await run_blocking(remove_shopping_items_by_numbers, numbers)
                logging.info(
                    "shopping_remove user_id=%s username=%s numbers=%s items=%s status=success",
                    user_id,
                    message.from_user.username if message.from_user else None,
                    ",".join(number_tokens),
                    ",".join(removed_items),
                )
                await message.answer(f"Удалено ({len(removed_items)}): {', '.join(removed_items)}")
        except ValueError:
            await message.answer(
                "Неверный номер, попробуйте снова",
                reply_markup=build_shopping_cancel_keyboard(session.session_id),
            )
            return
        except Exception:
            logging.exception("Ошибка удаления позиции из списка покупок")
            await message.answer("Не удалось обновить список покупок. Попробуйте позже.")
            return

        await _show_shopping_list(message, user_id)
        return

    await message.answer(
        "Используйте кнопки текущего шага или нажмите Отмена.",
        reply_markup=build_shopping_cancel_keyboard(session.session_id),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("sh:cancel:"))
async def shopping_cancel_handler(callback: types.CallbackQuery) -> None:
    if not await check_access_callback(callback):
        return
    user_id = callback.from_user.id
    session_id = callback.data.split(":")[2]
    if is_stale_session(user_id, session_id):
        await callback.answer("Шаг устарел, начните заново", show_alert=True)
        return
    await _cancel_shopping_flow(user_id, callback)


@router.callback_query(lambda c: c.data and c.data.startswith("sh:act:"))
async def shopping_action_handler(callback: types.CallbackQuery) -> None:
    if not await check_access_callback(callback):
        return
    if callback.message is None:
        await callback.answer("Ошибка сообщения.", show_alert=True)
        return

    user_id = callback.from_user.id
    _, _, session_id, action = callback.data.split(":", 3)
    if is_stale_session(user_id, session_id):
        await callback.answer("Шаг устарел, начните заново", show_alert=True)
        return

    session = get_active_session(user_id)
    if session is None:
        await callback.answer("Шаг устарел, начните заново", show_alert=True)
        return

    if action == "add":
        session.state = "await_add_text"
        touch_session(session)
        await _safe_delete_prompt(callback.bot, session.step_chat_id, session.step_message_id)
        prompt = await callback.message.answer(
            "Введите позицию для списка покупок. Можно добавить несколько через запятую.",
            reply_markup=build_shopping_cancel_keyboard(session.session_id),
        )
        session.step_chat_id = prompt.chat.id
        session.step_message_id = prompt.message_id
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
            await callback.answer()
            await callback.message.answer("Список пуст, удалять нечего")
            return

        session.state = "await_remove_number"
        touch_session(session)
        await _safe_delete_prompt(callback.bot, session.list_chat_id, session.list_message_id)
        await _safe_delete_prompt(callback.bot, session.step_chat_id, session.step_message_id)
        lines = ["Введите номер позиции для удаления:"]
        lines.append("Можно указать несколько номеров через запятую.")
        for idx, item in enumerate(items, start=1):
            lines.append(f"{idx}. {item}")
        prompt = await callback.message.answer(
            "\n".join(lines),
            reply_markup=build_shopping_cancel_keyboard(session.session_id),
        )
        session.step_chat_id = prompt.chat.id
        session.step_message_id = prompt.message_id
        session.list_chat_id = None
        session.list_message_id = None
        touch_session(session)
        await callback.answer()
        return

    if action == "clear":
        session.state = "await_clear_confirm"
        touch_session(session)
        await _safe_delete_prompt(callback.bot, session.list_chat_id, session.list_message_id)
        await _safe_delete_prompt(callback.bot, session.step_chat_id, session.step_message_id)
        prompt = await callback.message.answer(
            "Очистить весь список покупок?",
            reply_markup=build_shopping_clear_confirm_keyboard(session.session_id),
        )
        session.step_chat_id = prompt.chat.id
        session.step_message_id = prompt.message_id
        session.list_chat_id = None
        session.list_message_id = None
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
    if callback.message:
        await callback.message.answer("Список покупок очищен")
    await _show_shopping_list_callback(callback, user_id)
