import logging
from html import escape

from aiogram import Router, types

from constants import MENU_EXPENSES_CALLBACK, MENU_EXPENSES_TEXT
from keyboards.expenses import (
    build_cancel_keyboard,
    build_expense_categories_keyboard,
    build_saved_expense_actions_keyboard,
    build_saved_expense_edit_keyboard,
    build_expense_subcategories_keyboard,
    build_money_sources_keyboard,
)
from services.async_tools import run_blocking
from services.access import check_access_callback, check_access_message, is_allowed_username, is_allowed_user
from config import PROFILE, TRACK_MONEY_SOURCE
from services.money_sources import get_money_sources
from services.budget import get_budget_limits, get_category_details, get_subcategories_for_category
from services.expenses import (
    StaleExpenseError,
    delete_expense,
    parse_amount_with_optional_comment,
    update_expense,
    write_expense,
)
from services.money import currency_symbol
from services.settings_middleware import abandon_sessions
from state.dialog_messages import close_dialog, dialog_hint, dialog_result, dialog_step
from state.expense_session import (
    create_session,
    get_active_session,
    is_stale_session,
    new_session_id,
    pop_session,
    touch_session,
)
from state.saved_expense_actions import (
    SAVED_EXPENSE_ACTION_TTL_SECONDS,
    create_saved_expense_action,
    finalize_saved_expense_action,
    get_saved_expense_action,
    is_stale_saved_expense_action,
    touch_saved_expense_action,
    update_saved_expense_action,
)

router = Router()


def _saved_edit_keyboard(action_id):
    if TRACK_MONEY_SOURCE:
        return build_saved_expense_edit_keyboard(action_id, include_source=True)
    return build_saved_expense_edit_keyboard(action_id)


async def _category_summary(category_name: str) -> str:
    if not category_name:
        return ""

    from services.budget_views import format_category_card
    try:
        details = await run_blocking(get_category_details, category_name)
        return format_category_card(details)
    except Exception:
        logging.exception("Ошибка чтения категории после добавления траты")
        return ""


async def _expense_receipt(message, summary, category, action_id):
    text = "\n".join(summary)
    category_summary = await _category_summary(category)
    if category_summary and len(text) + len(category_summary) + 2 <= 4096:
        text += f"\n\n{category_summary}"
    await dialog_result(message, text, reply_markup=build_saved_expense_actions_keyboard(action_id),
                        ttl=SAVED_EXPENSE_ACTION_TTL_SECONDS)


async def _show_expense_category_step(message: types.Message, user_id: int) -> None:
    finalize_saved_expense_action(user_id)
    try:
        _, categories = await run_blocking(get_budget_limits)
    except Exception:
        logging.exception("Ошибка чтения категорий из Google Sheets")
        await dialog_step(message, "Не удалось загрузить категории. Попробуйте позже.")
        return

    if not categories:
        await dialog_step(message, "Категории не найдены в таблице.")
        return

    session = create_session(user_id=user_id, state="choose_category")
    session.category_options = tuple(categories)
    await dialog_step(
        message,
        "Введите категорию",
        reply_markup=build_expense_categories_keyboard(categories, session.session_id),
    )


async def _show_repeat_expense_amount_step(
    message: types.Message,
    user_id: int,
    category: str,
    subcategory: str,
) -> None:
    finalize_saved_expense_action(user_id)
    session = create_session(user_id=user_id, state="enter_amount")
    session.category = category
    session.subcategory = subcategory
    if TRACK_MONEY_SOURCE:
        await _show_source_step(message, user_id, session)
        return
    await dialog_step(
        message,
        f"Категория: {escape(category)}\nПодкатегория: {escape(subcategory)}\nВведите сумму (можно сразу с комментарием)",
        reply_markup=build_cancel_keyboard(session.session_id),
    )


def _source_session_current(user_id, session):
    if get_active_session(user_id) is not session or session.finalized:
        return False
    if session.saved_action_id:
        action = get_saved_expense_action(user_id)
        return bool(action and action.action_id == session.saved_action_id)
    return True


async def _show_source_step(message, user_id, session, *, unavailable=False):
    if not _source_session_current(user_id, session):
        return
    # Every rendered source snapshot owns fresh callback IDs. Indices from a
    # prior keyboard must never address a refreshed (possibly shorter) list.
    session.session_id = new_session_id()
    picker_id = session.session_id
    session.state = "choose_saved_source" if session.saved_action_id else "choose_source"
    session.source_options = ()
    try:
        sources = await run_blocking(get_money_sources)
    except Exception:
        sources = []
    if not _source_session_current(user_id, session) or session.session_id != picker_id:
        return
    if not sources:
        await dialog_step(message, "Нет доступных источников. Проверьте лист «Источники»: название, активно и порядок; затем начните шаг заново.", reply_markup=build_cancel_keyboard(session.session_id))
        return
    session.source_options = tuple(sources)
    prompt = "Источник больше недоступен. Выберите действующий источник." if unavailable else "Выберите источник денег"
    await dialog_step(message, prompt,
                      reply_markup=build_money_sources_keyboard(session.source_options, session.session_id))
    touch_session(session)


async def _cancel_expense_flow(user_id: int) -> None:
    pop_session(user_id)
    await close_dialog()


async def _finalize_expense(
    user_id: int,
    username: str | None,
    message_target: types.Message,
    comment: str | None = None,
) -> None:
    session = get_active_session(user_id)
    if session is None or session.state not in {"enter_amount", "await_confirm"}:
        await dialog_hint(message_target, "Шаг устарел, начните заново.")
        return

    try:
        if PROFILE.legacy:
            is_allowed, reason = await run_blocking(is_allowed_username, username)
        else:
            is_allowed, reason = await run_blocking(is_allowed_user, user_id, username)
    except Exception:
        logging.exception("Ошибка повторной проверки доступа перед записью траты")
        await dialog_hint(message_target, "Ошибка проверки доступа. Попробуйте позже.")
        return

    if get_active_session(user_id) is not session:
        return
    if not is_allowed:
        pop_session(user_id)
        if reason == "empty_username":
            await dialog_step(message_target, "Доступ запрещен. Установите username в Telegram.")
            return
        await dialog_step(message_target, "Доступ запрещен.")
        return

    category = session.category or ""
    subcategory = session.subcategory or ""
    amount = session.amount or ""
    final_comment = (session.comment or "") if comment is None else comment
    actor_username = f"@{username}" if username else ("" if PROFILE.legacy else str(user_id))
    source_kwargs = {}
    if TRACK_MONEY_SOURCE:
        try:
            sources = await run_blocking(get_money_sources)
        except Exception:
            sources = []
        if not _source_session_current(user_id, session):
            return
        if not session.money_source or session.money_source not in sources:
            await _show_source_step(message_target, user_id, session, unavailable=True)
            return
        source_kwargs["money_source"] = session.money_source

    try:
        saved_expense = await run_blocking(
            write_expense,
            username=actor_username,
            category=category,
            subcategory=subcategory,
            amount=amount,
            comment=final_comment,
            **source_kwargs,
        )
    except Exception:
        logging.exception("Ошибка записи траты в Google Sheets")
        await dialog_hint(message_target, "Не удалось добавить трату. Попробуйте позже.")
        return

    if get_active_session(user_id) is not session:
        return
    session.finalized = True
    pop_session(user_id)

    summary = [
        "Трата добавлена.",
        f"Категория: {escape(category)}",
        f"Подкатегория: {escape(subcategory)}",
        f"Сумма: {amount} {currency_symbol()}",
    ]
    if final_comment:
        summary.append(f"Комментарий: {escape(final_comment)}")
    if TRACK_MONEY_SOURCE:
        summary.append(f"Источник: {escape(session.money_source or 'Не указан')}")

    action = create_saved_expense_action(user_id, saved_expense)

    logging.info(
        "expense_added user_id=%s username=%s category=%s subcategory=%s amount=%s row_number=%s",
        user_id,
        username,
        category,
        subcategory,
        amount,
        getattr(saved_expense, "row_number", None),
    )
    await _expense_receipt(message_target, summary, category, action.action_id)


async def _update_saved_expense(
    user_id: int,
    message_target: types.Message,
    amount: str,
    comment: str,
    *, money_source: str | None = None,
) -> None:
    session = get_active_session(user_id)
    if session is None or session.state not in {"edit_saved_expense", "choose_saved_source"} or not session.saved_action_id:
        await dialog_hint(message_target, "Шаг устарел, начните заново.")
        return

    action = get_saved_expense_action(user_id)
    if action is None or action.action_id != session.saved_action_id:
        pop_session(user_id)
        await dialog_step(message_target, "Кнопки устарели. Начните заново.")
        return

    source_kwargs = {"money_source": money_source} if TRACK_MONEY_SOURCE and money_source is not None else {}
    previous_state = session.state
    if source_kwargs:
        session.state = "saving_saved_source"
    try:
        saved_expense = await run_blocking(update_expense, action.saved_expense, amount, comment, **source_kwargs)
    except StaleExpenseError:
        logging.warning("Попытка изменить устаревшую трату user_id=%s", user_id)
        if _source_session_current(user_id, session):
            pop_session(user_id)
            finalize_saved_expense_action(user_id)
        await dialog_step(message_target, "Трата уже изменилась. Начните заново.")
        return
    except Exception:
        logging.exception("Ошибка изменения траты в Google Sheets")
        if _source_session_current(user_id, session):
            session.state = previous_state
        await dialog_hint(message_target, "Не удалось изменить трату. Попробуйте позже.")
        return

    if not _source_session_current(user_id, session) or get_saved_expense_action(user_id) is not action:
        return
    update_saved_expense_action(user_id, saved_expense)
    pop_session(user_id)
    summary = [
        "Трата обновлена.",
        f"Категория: {escape(saved_expense.category)}",
        f"Подкатегория: {escape(saved_expense.subcategory)}",
        f"Сумма: {saved_expense.amount} {currency_symbol()}",
    ]
    if TRACK_MONEY_SOURCE:
        summary.append(f"Источник: {escape(saved_expense.money_source or 'Не указан')}")
    if saved_expense.comment:
        summary.append(f"Комментарий: {escape(saved_expense.comment)}")
    await _expense_receipt(message_target, summary, saved_expense.category, action.action_id)


@router.message(
    lambda message: bool(message.text) and message.text.endswith(MENU_EXPENSES_TEXT)
)
async def start_expense_flow(message: types.Message) -> None:
    if not await check_access_message(message):
        return
    user_id = message.from_user.id if message.from_user else 0
    await _show_expense_category_step(message, user_id)


@router.callback_query(lambda c: c.data == MENU_EXPENSES_CALLBACK)
async def start_expense_flow_callback(callback: types.CallbackQuery) -> None:
    if not await check_access_callback(callback):
        return
    await callback.answer()
    if callback.message is None or isinstance(callback.message, types.InaccessibleMessage):
        return
    user_id = callback.from_user.id
    abandon_sessions(user_id)
    await _show_expense_category_step(callback.message, user_id)


@router.message(lambda message: bool(message.from_user and get_active_session(message.from_user.id)))
async def expense_text_step(message: types.Message) -> None:
    if not await check_access_message(message):
        return
    if not message.text:
        return

    user_id = message.from_user.id if message.from_user else 0
    session = get_active_session(user_id)
    if session is None:
        await dialog_step(message, "Шаг устарел, начните заново.")
        return

    if message.text.strip().lower() in {"отмена", "/cancel"}:
        await _cancel_expense_flow(user_id)
        return
    touch_session(session)

    if session.state == "enter_amount":
        try:
            normalized_amount, inline_comment = parse_amount_with_optional_comment(message.text)
        except ValueError as exc:
            await dialog_hint(message, f"Некорректная сумма: {escape(str(exc))}.")
            return

        session.amount = normalized_amount
        session.comment = inline_comment or None
        touch_session(session)
        await _finalize_expense(
            user_id=user_id,
            username=message.from_user.username if message.from_user else None,
            message_target=message,
            comment=session.comment or "",
        )
        return

    if session.state == "await_confirm":
        comment = message.text.strip()
        await _finalize_expense(
            user_id=user_id,
            username=message.from_user.username if message.from_user else None,
            message_target=message,
            comment=comment,
        )
        return

    if session.state == "edit_saved_expense":
        try:
            normalized_amount, inline_comment = parse_amount_with_optional_comment(message.text)
        except ValueError as exc:
            await dialog_hint(message, f"Некорректная сумма: {escape(str(exc))}.")
            return

        await _update_saved_expense(
            user_id=user_id,
            message_target=message,
            amount=normalized_amount,
            comment=inline_comment,
        )
        return

    await dialog_hint(message, "Используйте кнопки текущего шага или отправьте /cancel.")


@router.callback_query(lambda c: c.data and c.data.startswith("exp:cancel:"))
async def expense_cancel_handler(callback: types.CallbackQuery) -> None:
    if not await check_access_callback(callback):
        return

    user_id = callback.from_user.id
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer("Некорректная кнопка", show_alert=True)
        return
    session_id = parts[2]
    if is_stale_session(user_id, session_id):
        await callback.answer("Шаг устарел, начните заново", show_alert=True)
        return

    await _cancel_expense_flow(user_id)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("exp:cat:"))
async def expense_category_handler(callback: types.CallbackQuery) -> None:
    if not await check_access_callback(callback):
        return

    user_id = callback.from_user.id
    _, _, session_id, idx_raw = callback.data.split(":", 3)
    if is_stale_session(user_id, session_id):
        await callback.answer("Шаг устарел, начните заново", show_alert=True)
        return

    session = get_active_session(user_id)
    if session is None or session.state != "choose_category":
        await callback.answer("Шаг устарел, начните заново", show_alert=True)
        return

    if not idx_raw.isdigit():
        await callback.answer("Некорректная категория", show_alert=True)
        return

    try:
        _, categories = await run_blocking(get_budget_limits)
        idx = int(idx_raw)
        if session.category_options and session.category_options != tuple(categories):
            await callback.answer("Список категорий изменился. Начните заново.", show_alert=True)
            return
        if idx < 0 or idx >= len(categories):
            await callback.answer("Шаг устарел, начните заново", show_alert=True)
            return

        category_name = categories[idx]
        subcategories = await run_blocking(get_subcategories_for_category, category_name)
    except Exception:
        logging.exception("Ошибка чтения категорий/подкатегорий")
        await callback.answer("Ошибка чтения данных", show_alert=True)
        return

    # A Sheets read yields control. Never continue a replaced/cancelled flow
    # using the old session object, even when called outside the dispatcher.
    if get_active_session(user_id) is not session or session.state != "choose_category":
        await callback.answer("Шаг устарел, начните заново", show_alert=True)
        return

    if not subcategories:
        await callback.answer("У категории нет подкатегорий. Начните заново.", show_alert=True)
        await _cancel_expense_flow(user_id)
        return

    session.category = category_name
    session.state = "choose_subcategory"
    session.subcategory_options = tuple(subcategories)
    touch_session(session)

    if callback.message is None or isinstance(callback.message, types.InaccessibleMessage):
        await callback.answer("Ошибка сообщения.", show_alert=True)
        return
    await dialog_step(
        callback.message,
        f"Категория: {escape(category_name)}\nВыберите подкатегорию",
        reply_markup=build_expense_subcategories_keyboard(subcategories, session.session_id),
    )
    touch_session(session)

    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("exp:sub:"))
async def expense_subcategory_handler(callback: types.CallbackQuery) -> None:
    if not await check_access_callback(callback):
        return

    user_id = callback.from_user.id
    _, _, session_id, idx_raw = callback.data.split(":", 3)
    if is_stale_session(user_id, session_id):
        await callback.answer("Шаг устарел, начните заново", show_alert=True)
        return

    session = get_active_session(user_id)
    if session is None or session.state != "choose_subcategory" or not session.category:
        await callback.answer("Шаг устарел, начните заново", show_alert=True)
        return

    if not idx_raw.isdigit():
        await callback.answer("Некорректная подкатегория", show_alert=True)
        return

    try:
        subcategories = await run_blocking(get_subcategories_for_category, session.category)
        idx = int(idx_raw)
        if session.subcategory_options and session.subcategory_options != tuple(subcategories):
            await callback.answer("Список подкатегорий изменился. Начните заново.", show_alert=True)
            return
        if idx < 0 or idx >= len(subcategories):
            await callback.answer("Шаг устарел, начните заново", show_alert=True)
            return
    except Exception:
        logging.exception("Ошибка чтения подкатегорий")
        await callback.answer("Ошибка чтения данных", show_alert=True)
        return

    if get_active_session(user_id) is not session or session.state != "choose_subcategory":
        await callback.answer("Шаг устарел, начните заново", show_alert=True)
        return

    session.subcategory = subcategories[idx]
    session.state = "choose_source" if TRACK_MONEY_SOURCE else "enter_amount"
    touch_session(session)

    if callback.message is None or isinstance(callback.message, types.InaccessibleMessage):
        await callback.answer("Ошибка сообщения.", show_alert=True)
        return
    if TRACK_MONEY_SOURCE:
        await _show_source_step(callback.message, user_id, session)
        await callback.answer()
        return
    await dialog_step(
        callback.message,
        f"Категория: {escape(session.category)}\nПодкатегория: {escape(session.subcategory)}\nВведите сумму (можно сразу с комментарием)",
        reply_markup=build_cancel_keyboard(session.session_id),
    )
    touch_session(session)

    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("exp:src:"))
async def expense_source_handler(callback: types.CallbackQuery) -> None:
    if not await check_access_callback(callback):
        return
    parts = (callback.data or "").split(":")
    user_id = callback.from_user.id
    session = get_active_session(user_id)
    if (not TRACK_MONEY_SOURCE or len(parts) != 4 or session is None
            or parts[2] != session.session_id or not parts[3].isascii()
            or not parts[3].isdigit() or len(parts[3]) > 6
            or session.state not in {"choose_source", "choose_saved_source"}
            or not _source_session_current(user_id, session) or callback.message is None
            or isinstance(callback.message, types.InaccessibleMessage)):
        await callback.answer("Шаг устарел или кнопка некорректна", show_alert=True)
        return
    index = int(parts[3])
    if index >= len(session.source_options):
        await callback.answer("Некорректный источник", show_alert=True)
        return
    source = session.source_options[index]
    previous_state = session.state
    session.state = "checking_source"
    try:
        sources = await run_blocking(get_money_sources)
    except Exception:
        sources = []
    if not _source_session_current(user_id, session) or session.state != "checking_source":
        await callback.answer("Шаг устарел", show_alert=True)
        return
    session.state = previous_state
    if source not in sources:
        await _show_source_step(callback.message, user_id, session)
        await callback.answer("Источник недоступен. Выберите действующий источник.", show_alert=True)
        return
    session.money_source = source
    touch_session(session)
    if session.saved_action_id:
        action = get_saved_expense_action(user_id)
        await callback.answer()
        if not _source_session_current(user_id, session) or action is not get_saved_expense_action(user_id):
            return
        await _update_saved_expense(user_id, callback.message, action.saved_expense.amount,
                                    action.saved_expense.comment, money_source=source)
        return
    session.state = "enter_amount"
    if not _source_session_current(user_id, session):
        return
    await dialog_step(
        callback.message,
        f"Источник: {escape(source)}\nВведите сумму (можно сразу с комментарием)",
        reply_markup=build_cancel_keyboard(session.session_id))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("exp:yes:"))
async def expense_confirm_handler(callback: types.CallbackQuery) -> None:
    if not await check_access_callback(callback):
        return

    user_id = callback.from_user.id
    session_id = callback.data.split(":")[2]
    if is_stale_session(user_id, session_id):
        await callback.answer("Шаг устарел, начните заново", show_alert=True)
        return

    session = get_active_session(user_id)
    if session is None or session.state != "await_confirm":
        await callback.answer("Шаг устарел, начните заново", show_alert=True)
        return

    await callback.answer()
    if isinstance(callback.message, types.Message):
        await _finalize_expense(
            user_id=user_id,
            username=callback.from_user.username if callback.from_user else None,
            message_target=callback.message,
            comment=None,
        )


@router.callback_query(lambda c: c.data and c.data.startswith("exp:saved:"))
async def saved_expense_action_handler(callback: types.CallbackQuery) -> None:
    if not await check_access_callback(callback):
        return

    user_id = callback.from_user.id
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        await callback.answer("Некорректная кнопка", show_alert=True)
        return
    _, _, action_name, action_id = parts
    if is_stale_saved_expense_action(user_id, action_id):
        await callback.answer("Кнопки устарели. Начните заново.", show_alert=True)
        return

    action = get_saved_expense_action(user_id)
    if action is None or callback.message is None:
        await callback.answer("Кнопки устарели. Начните заново.", show_alert=True)
        return

    touch_saved_expense_action(action)

    if action_name == "source" and TRACK_MONEY_SOURCE:
        session = create_session(user_id=user_id, state="choose_saved_source")
        session.saved_action_id = action.action_id
        await _show_source_step(callback.message, user_id, session)
        await callback.answer()
        return

    if action_name == "edit":
        session = create_session(user_id=user_id, state="edit_saved_expense")
        session.saved_action_id = action.action_id
        await dialog_step(
            callback.message,
            "Введите новую сумму. Можно сразу с комментарием.",
            reply_markup=_saved_edit_keyboard(action.action_id),
        )
        await callback.answer()
        return

    if action_name == "repeat":
        await callback.answer()
        await _show_repeat_expense_amount_step(
            callback.message,
            user_id,
            action.saved_expense.category,
            action.saved_expense.subcategory,
        )
        return

    if action_name == "fresh":
        await callback.answer()
        await _show_expense_category_step(callback.message, user_id)
        return

    if action_name == "delete":
        try:
            await run_blocking(delete_expense, action.saved_expense)
        except StaleExpenseError:
            logging.warning("Попытка удалить устаревшую трату user_id=%s", user_id)
            finalize_saved_expense_action(user_id)
            await close_dialog()
            await callback.answer("Трата уже изменилась. Начните заново.", show_alert=True)
            return
        except Exception:
            logging.exception("Ошибка удаления траты из Google Sheets")
            await callback.answer("Не удалось удалить трату.", show_alert=True)
            return

        pop_session(user_id)
        finalize_saved_expense_action(user_id)
        await callback.answer()
        await dialog_result(callback.message, "Трата удалена.")
        return

    if action_name == "cancel":
        pop_session(user_id)
        finalize_saved_expense_action(user_id)
        await close_dialog()
        await callback.answer()
        return

    await callback.answer("Неизвестное действие.", show_alert=True)
