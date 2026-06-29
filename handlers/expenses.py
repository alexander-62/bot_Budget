import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from aiogram import Router, types

from constants import MENU_EXPENSES_CALLBACK, MENU_EXPENSES_TEXT
from keyboards.expenses import (
    build_cancel_keyboard,
    build_confirm_keyboard,
    build_expense_categories_keyboard,
    build_saved_expense_actions_keyboard,
    build_saved_expense_edit_keyboard,
    build_expense_subcategories_keyboard,
)
from keyboards.limits import build_category_actions_keyboard
from keyboards.main import build_main_menu
from services.async_tools import run_blocking
from services.access import check_access_callback, check_access_message, is_allowed_username
from services.budget import get_budget_limits, get_category_details, get_subcategories_for_category
from services.expenses import (
    StaleExpenseError,
    delete_expense,
    parse_amount_with_optional_comment,
    update_expense,
    write_expense,
)
from state.expense_session import (
    create_session,
    get_active_session,
    is_stale_session,
    pop_session,
    touch_session,
)
from state.saved_expense_actions import (
    create_saved_expense_action,
    finalize_saved_expense_action,
    get_saved_expense_action,
    is_stale_saved_expense_action,
    touch_saved_expense_action,
    update_saved_expense_action,
)

router = Router()


async def _safe_delete_prompt(bot, chat_id: int | None, message_id: int | None) -> None:
    if chat_id is None or message_id is None:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        logging.exception("Не удалось удалить сообщение шага")


def _parse_sheet_number(value: str) -> Decimal:
    normalized = value.replace("\xa0", "").replace(" ", "").replace("€", "").replace(",", ".")
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(f"Некорректное число: {value}") from exc


def _format_eur_rounded(value: str) -> str:
    rounded = _parse_sheet_number(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{int(rounded):,}".replace(",", " ")


def _format_money_or_dash(value: str) -> str:
    value = value.strip()
    if not value or value == "—" or value == "не указан":
        return "—"
    return f"{_format_eur_rounded(value)} €"


def _format_remaining_with_alert(value: str) -> str:
    value = value.strip()
    if not value or value == "—" or value == "не указан":
        return "—"

    dec_value = _parse_sheet_number(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    formatted = f"{int(dec_value):,}".replace(",", " ") + " €"
    if dec_value < 0:
        return f"{formatted} ⚠️"
    return formatted


async def _show_category_card(message_target: types.Message, category_name: str) -> None:
    if not category_name:
        return

    try:
        (
            category_title,
            category_limit,
            category_spent,
            category_remaining,
            subcategories,
        ) = await run_blocking(get_category_details, category_name)
    except Exception:
        logging.exception("Ошибка чтения категории после добавления траты")
        await message_target.answer("Трата добавлена, но не удалось загрузить карточку категории.")
        return

    category_limit_fmt = _format_money_or_dash(category_limit)
    category_spent_fmt = _format_money_or_dash(category_spent)
    category_remaining_fmt = _format_remaining_with_alert(category_remaining)

    lines = [
        f"🏷️ <b>{category_title}</b>",
        "📊 Лимит / Потрачено / Осталось",
        f"<b>{category_limit_fmt} / {category_spent_fmt} / {category_remaining_fmt}</b>",
        "",
        "🧾 Подкатегории:",
    ]
    if subcategories:
        for sub_name, sub_limit, sub_spent, sub_remaining in subcategories:
            sub_limit_fmt = _format_money_or_dash(sub_limit)
            sub_spent_fmt = _format_money_or_dash(sub_spent)
            sub_remaining_fmt = _format_remaining_with_alert(sub_remaining)
            lines.append(f"👉<b>{sub_name}</b>")
            lines.append("Лимит / Потрачено / Осталось")
            lines.append(f"<b>{sub_limit_fmt} / {sub_spent_fmt} / {sub_remaining_fmt}</b>")
            lines.append("")
    else:
        lines.append("- нет подкатегорий")

    await message_target.answer(
        "\n".join(lines).strip(),
        reply_markup=build_category_actions_keyboard(),
    )


async def _show_expense_category_step(message: types.Message, user_id: int) -> None:
    finalize_saved_expense_action(user_id)
    try:
        _, categories = await run_blocking(get_budget_limits)
    except Exception:
        logging.exception("Ошибка чтения категорий из Google Sheets")
        await message.answer("Не удалось загрузить категории. Попробуйте позже.")
        return

    if not categories:
        await message.answer("Категории не найдены в таблице.")
        return

    session = create_session(user_id=user_id, state="choose_category")
    prompt = await message.answer(
        "Введите категорию",
        reply_markup=build_expense_categories_keyboard(categories, session.session_id),
    )
    session.prompt_chat_id = prompt.chat.id
    session.prompt_message_id = prompt.message_id


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
    prompt = await message.answer(
        f"Категория: {category}\nПодкатегория: {subcategory}\nВведите сумму (можно сразу с комментарием)",
        reply_markup=build_cancel_keyboard(session.session_id),
    )
    session.prompt_chat_id = prompt.chat.id
    session.prompt_message_id = prompt.message_id


async def _cancel_expense_flow(
    user_id: int, notify_target: types.Message | types.CallbackQuery
) -> None:
    session = pop_session(user_id)
    if session:
        target_bot = notify_target.bot
        await _safe_delete_prompt(target_bot, session.prompt_chat_id, session.prompt_message_id)

    if isinstance(notify_target, types.CallbackQuery):
        await notify_target.answer("Добавление траты отменено", show_alert=False)
        if notify_target.message:
            await notify_target.message.answer("Добавление траты отменено.")
        return

    await notify_target.answer("Добавление траты отменено.")


async def _finalize_expense(
    user_id: int,
    username: str | None,
    message_target: types.Message,
    comment: str | None = None,
) -> None:
    session = get_active_session(user_id)
    if session is None or session.state not in {"enter_amount", "await_confirm"}:
        await message_target.answer("Шаг устарел, начните заново.")
        return

    try:
        is_allowed, reason = await run_blocking(is_allowed_username, username)
    except Exception:
        logging.exception("Ошибка повторной проверки доступа перед записью траты")
        await message_target.answer("Ошибка проверки доступа. Попробуйте позже.")
        return

    if not is_allowed:
        pop_session(user_id)
        if reason == "empty_username":
            await message_target.answer("Доступ запрещен. Установите username в Telegram.")
            return
        await message_target.answer("Доступ запрещен.")
        return

    category = session.category or ""
    subcategory = session.subcategory or ""
    amount = session.amount or ""
    final_comment = (session.comment or "") if comment is None else comment
    actor_username = f"@{username}" if username else ""

    try:
        saved_expense = await run_blocking(
            write_expense,
            username=actor_username,
            category=category,
            subcategory=subcategory,
            amount=amount,
            comment=final_comment,
        )
    except Exception:
        logging.exception("Ошибка записи траты в Google Sheets")
        await message_target.answer("Не удалось добавить трату. Попробуйте позже.")
        return

    session.finalized = True
    pop_session(user_id)
    await _safe_delete_prompt(message_target.bot, session.prompt_chat_id, session.prompt_message_id)

    summary = [
        "Трата добавлена.",
        f"Категория: {category}",
        f"Подкатегория: {subcategory}",
        f"Сумма: {amount}",
    ]
    if final_comment:
        summary.append(f"Комментарий: {final_comment}")

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
    await message_target.answer(
        "\n".join(summary),
        reply_markup=build_saved_expense_actions_keyboard(action.action_id),
    )
    await _show_category_card(message_target, category)


async def _update_saved_expense(
    user_id: int,
    message_target: types.Message,
    amount: str,
    comment: str,
) -> None:
    session = get_active_session(user_id)
    if session is None or session.state != "edit_saved_expense" or not session.saved_action_id:
        await message_target.answer("Шаг устарел, начните заново.")
        return

    action = get_saved_expense_action(user_id)
    if action is None or action.action_id != session.saved_action_id:
        pop_session(user_id)
        await message_target.answer("Кнопки устарели. Начните заново.")
        return

    try:
        saved_expense = await run_blocking(update_expense, action.saved_expense, amount, comment)
    except StaleExpenseError:
        logging.warning("Попытка изменить устаревшую трату user_id=%s", user_id)
        pop_session(user_id)
        finalize_saved_expense_action(user_id)
        await message_target.answer("Трата уже изменилась. Начните заново.")
        return
    except Exception:
        logging.exception("Ошибка изменения траты в Google Sheets")
        await message_target.answer("Не удалось изменить трату. Попробуйте позже.")
        return

    update_saved_expense_action(user_id, saved_expense)
    pop_session(user_id)
    await _safe_delete_prompt(message_target.bot, session.prompt_chat_id, session.prompt_message_id)
    await message_target.answer(
        "\n".join(
            [
                "Трата обновлена.",
                f"Категория: {saved_expense.category}",
                f"Подкатегория: {saved_expense.subcategory}",
                f"Сумма: {saved_expense.amount}",
                *( [f"Комментарий: {saved_expense.comment}"] if saved_expense.comment else [] ),
            ]
        ),
        reply_markup=build_saved_expense_actions_keyboard(action.action_id),
    )
    await _show_category_card(message_target, saved_expense.category)


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
    if callback.message is None:
        return
    user_id = callback.from_user.id if callback.from_user else 0
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
        await message.answer("Шаг устарел, начните заново.")
        return

    touch_session(session)

    if session.state == "enter_amount":
        try:
            normalized_amount, inline_comment = parse_amount_with_optional_comment(message.text)
        except ValueError as exc:
            await message.answer(
                f"Некорректная сумма: {exc}. Введите сумму еще раз.",
                reply_markup=build_cancel_keyboard(session.session_id),
            )
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
            await message.answer(
                f"Некорректная сумма: {exc}. Введите сумму еще раз.",
                reply_markup=build_saved_expense_edit_keyboard(session.saved_action_id or ""),
            )
            return

        await _update_saved_expense(
            user_id=user_id,
            message_target=message,
            amount=normalized_amount,
            comment=inline_comment,
        )
        return

    await message.answer(
        "Используйте кнопки текущего шага или нажмите Отмена.",
        reply_markup=build_cancel_keyboard(session.session_id),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("exp:cancel:"))
async def expense_cancel_handler(callback: types.CallbackQuery) -> None:
    if not await check_access_callback(callback):
        return

    user_id = callback.from_user.id
    session_id = callback.data.split(":")[2]
    if is_stale_session(user_id, session_id):
        await callback.answer("Шаг устарел, начните заново", show_alert=True)
        return

    await _cancel_expense_flow(user_id, callback)


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
        if idx < 0 or idx >= len(categories):
            await callback.answer("Шаг устарел, начните заново", show_alert=True)
            return

        category_name = categories[idx]
        subcategories = await run_blocking(get_subcategories_for_category, category_name)
    except Exception:
        logging.exception("Ошибка чтения категорий/подкатегорий")
        await callback.answer("Ошибка чтения данных", show_alert=True)
        return

    if not subcategories:
        await callback.answer()
        if callback.message:
            await callback.message.answer("У категории нет подкатегорий. Начните заново.")
        pop_session(user_id)
        return

    session.category = category_name
    session.state = "choose_subcategory"
    touch_session(session)

    await _safe_delete_prompt(callback.bot, session.prompt_chat_id, session.prompt_message_id)
    if callback.message is None:
        await callback.answer("Ошибка сообщения.", show_alert=True)
        return
    prompt = await callback.message.answer(
        f"Категория: {category_name}\nВыберите подкатегорию",
        reply_markup=build_expense_subcategories_keyboard(subcategories, session.session_id),
    )
    session.prompt_chat_id = prompt.chat.id
    session.prompt_message_id = prompt.message_id
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
        if idx < 0 or idx >= len(subcategories):
            await callback.answer("Шаг устарел, начните заново", show_alert=True)
            return
    except Exception:
        logging.exception("Ошибка чтения подкатегорий")
        await callback.answer("Ошибка чтения данных", show_alert=True)
        return

    session.subcategory = subcategories[idx]
    session.state = "enter_amount"
    touch_session(session)

    await _safe_delete_prompt(callback.bot, session.prompt_chat_id, session.prompt_message_id)
    if callback.message is None:
        await callback.answer("Ошибка сообщения.", show_alert=True)
        return
    prompt = await callback.message.answer(
        f"Категория: {session.category}\nПодкатегория: {session.subcategory}\nВведите сумму (можно сразу с комментарием)",
        reply_markup=build_cancel_keyboard(session.session_id),
    )
    session.prompt_chat_id = prompt.chat.id
    session.prompt_message_id = prompt.message_id
    touch_session(session)

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
    if callback.message:
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
    _, _, action_name, action_id = callback.data.split(":", 3)
    if is_stale_saved_expense_action(user_id, action_id):
        await callback.answer("Кнопки устарели. Начните заново.", show_alert=True)
        return

    action = get_saved_expense_action(user_id)
    if action is None or callback.message is None:
        await callback.answer("Кнопки устарели. Начните заново.", show_alert=True)
        return

    touch_saved_expense_action(action)

    if action_name == "edit":
        session = create_session(user_id=user_id, state="edit_saved_expense")
        session.saved_action_id = action.action_id
        prompt = await callback.message.answer(
            "Введите новую сумму. Можно сразу с комментарием.",
            reply_markup=build_saved_expense_edit_keyboard(action.action_id),
        )
        session.prompt_chat_id = prompt.chat.id
        session.prompt_message_id = prompt.message_id
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
            await callback.answer("Трата уже изменилась. Начните заново.", show_alert=True)
            return
        except Exception:
            logging.exception("Ошибка удаления траты из Google Sheets")
            await callback.answer("Не удалось удалить трату.", show_alert=True)
            return

        pop_session(user_id)
        finalize_saved_expense_action(user_id)
        await callback.answer()
        await callback.message.answer("Трата удалена.", reply_markup=build_main_menu())
        return

    if action_name == "cancel":
        pop_session(user_id)
        finalize_saved_expense_action(user_id)
        await callback.answer("Действие отменено", show_alert=False)
        if callback.message:
            await callback.message.answer("Действие отменено.")
        return

    await callback.answer("Неизвестное действие.", show_alert=True)
