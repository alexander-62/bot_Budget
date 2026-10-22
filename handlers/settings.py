import logging
from html import escape

from aiogram import Router, types
from keyboards.main import build_main_menu
from keyboards.settings import settings_keyboard, choice_keyboard
from services.access import check_access_message, check_access_callback
from services.async_tools import run_blocking
from services.budget import get_budget_limits
from services.budget_settings import refresh_runtime_settings, set_runtime_setting
from services.categories import create_category, create_subcategory, validate_name
from state.settings_session import create_session, get_session, pop_session, advance

router = Router()


def _clear_other_flows(user_id):
    from state.expense_session import pop_session as pop_expense
    from state.shopping_session import pop_session as pop_shopping
    from state.saved_expense_actions import finalize_saved_expense_action
    pop_expense(user_id)
    pop_shopping(user_id)
    finalize_saved_expense_action(user_id)


async def _menu(message, session):
    settings = await run_blocking(refresh_runtime_settings, force=True)
    advance(session, "menu")
    await message.answer("⚙️ Настройки бюджета — общие для всех участников.", reply_markup=settings_keyboard(session, settings))


async def _failure(message, error):
    if isinstance(error, ValueError):
        await message.answer(escape(str(error)))
    else:
        logging.exception("Ошибка настройки бюджета")
        await message.answer("Не удалось сохранить или загрузить данные. Повторите попытку; проверьте таблицу перед повторным созданием.")


@router.message(lambda m: m.text in {"⚙️ Настройки", "Настройки", "/settings"})
async def open_settings(message: types.Message):
    if not await check_access_message(message):
        return
    _clear_other_flows(message.from_user.id)
    session = create_session(message.from_user.id, message.chat.id)
    try:
        await _menu(message, session)
    except Exception as error:
        pop_session(message.from_user.id)
        await _failure(message, error)


@router.callback_query(lambda c: c.data and c.data.startswith("cfg:"))
async def settings_callback(callback: types.CallbackQuery):
    if not await check_access_callback(callback):
        return
    parts = callback.data.split(":")
    session = get_session(callback.from_user.id)
    if (len(parts) != 3 or session is None or session.token != parts[1]
            or callback.message is None or session.chat_id != callback.message.chat.id):
        await callback.answer("Эта кнопка устарела. Откройте настройки заново.", show_alert=True)
        return
    await callback.answer()
    message, action = callback.message, parts[2]
    try:
        if action == "cancel":
            pop_session(callback.from_user.id)
            await message.answer("Настройки закрыты.", reply_markup=build_main_menu())
        elif action == "back":
            await _menu(message, session)
        elif action == "currency" and session.step == "menu":
            advance(session, "currency")
            await message.answer("Выберите единую валюту бюджета.", reply_markup=choice_keyboard(session, [("₽ RUB", "RUB"), ("€ EUR", "EUR")]))
        elif action in {"EUR", "RUB"} and session.step == "currency":
            settings = await run_blocking(refresh_runtime_settings, force=True)
            session.currency = settings.currency
            advance(session, f"confirm_{action}")
            await message.answer(
                f"Изменить валюту {settings.currency} → {action}? Обозначение изменится у всех сумм, включая историю. Пересчёта по курсу не будет.",
                reply_markup=choice_keyboard(session, [("Подтвердить смену валюты", "confirm")]))
        elif action == "confirm" and session.step.startswith("confirm_"):
            currency = session.step.removeprefix("confirm_")
            await run_blocking(set_runtime_setting, "currency", currency, expected=session.currency)
            await message.answer("Валюта сохранена. Суммы не пересчитывались.", reply_markup=build_main_menu())
            await _menu(message, session)
        elif action == "limits" and session.step == "menu":
            advance(session, "limits")
            await message.answer("При выключении остаётся учёт трат. Сохранённые лимиты не удаляются.",
                                 reply_markup=choice_keyboard(session, [("🟢 Включить", "on"), ("⚪ Выключить", "off")]))
        elif action in {"on", "off"} and session.step == "limits":
            if action == "on":
                # Validate the optional sheet before enabling a mode that needs it.
                from services.budget_settings import validate_limits_sheet
                await run_blocking(validate_limits_sheet)
            await run_blocking(set_runtime_setting, "monthly_limits_enabled", "TRUE" if action == "on" else "FALSE")
            await message.answer("Месячные лимиты включены." if action == "on" else "Лимиты выключены. Продолжаем считать траты.", reply_markup=build_main_menu())
            await _menu(message, session)
        elif action == "new" and session.step == "menu":
            advance(session, "category_name")
            await message.answer("Введите название новой категории (до 64 символов).", reply_markup=choice_keyboard(session, []))
        elif action == "sub" and session.step == "menu":
            _, categories = await run_blocking(get_budget_limits)
            session.categories = tuple(categories)
            advance(session, "choose_category")
            await message.answer("Выберите категорию." if categories else "Активных категорий пока нет. Создайте первую.",
                                 reply_markup=choice_keyboard(session, [(name, f"cat{i}") for i, name in enumerate(categories)]))
        elif action.startswith("cat") and session.step == "choose_category":
            index = action[3:]
            if not index.isdigit() or int(index) >= len(session.categories):
                raise ValueError("Некорректная категория.")
            session.category = session.categories[int(index)]
            advance(session, "subcategory_name")
            await message.answer(f"Категория: {escape(session.category)}. Введите название подкатегории.", reply_markup=choice_keyboard(session, []))
        else:
            raise ValueError("Шаг устарел. Откройте настройки заново.")
    except Exception as error:
        await _failure(message, error)


@router.message(lambda m: bool(m.from_user and get_session(m.from_user.id)))
async def settings_text(message: types.Message):
    if not await check_access_message(message):
        return
    session = get_session(message.from_user.id)
    if session is None or session.chat_id != message.chat.id:
        return
    if message.text and message.text.strip().lower() in {"отмена", "/cancel"}:
        pop_session(message.from_user.id)
        await message.answer("Отменено.", reply_markup=build_main_menu())
        return
    try:
        if session.step not in {"category_name", "first_subcategory", "subcategory_name"}:
            await message.answer("Выберите действие кнопкой или нажмите «Отмена».")
            return
        name = validate_name(message.text or "")
        if session.step == "category_name":
            session.category = name
            advance(session, "first_subcategory")
            await message.answer(f"Категория: {escape(name)}. Введите первую подкатегорию.", reply_markup=choice_keyboard(session, []))
            return
        function = create_category if session.step == "first_subcategory" else create_subcategory
        category, subcategory = await run_blocking(function, session.category, name)
        advance(session, "saved")
        await message.answer(f"✅ Создано: {escape(category)} → {escape(subcategory)}")
        await _menu(message, session)
    except Exception as error:
        await _failure(message, error)
