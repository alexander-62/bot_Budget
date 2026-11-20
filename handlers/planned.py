"""Telegram UI for shared future expenses. Persisted IDs reopen after restart."""
import logging
from html import escape

from aiogram import Router, types
from config import PLANNED_EXPENSES_ENABLED, TRACK_MONEY_SOURCE
from constants import MENU_PLANNED_TEXT
from keyboards.main import build_main_menu
from keyboards.planned import actions
from services.access import check_access_message, check_access_callback
from services.async_tools import run_blocking
from services.budget import get_budget_limits, get_subcategories_for_category
from services.money import format_money_exact
from services import planned_expenses as plans
from state.planned_session import create_session, get_session, pop_session, advance

router = Router()
PAGE_SIZE = 8
NAVIGATION = {'📊 Посмотреть лимиты', 'Посмотреть лимиты', '📊 Расходы за месяц', 'Расходы за месяц',
              '🧾 Посмотреть траты', 'Посмотреть траты', '💸 Добавить трату', 'Добавить трату',
              '🛒 Список Покупок', 'Список Покупок', '⚙️ Настройки', 'Настройки', '/settings', '/start',
              '📅 Будущие траты', MENU_PLANNED_TEXT, '/planned', '🌐 Открыть Web App'}


def clear_other_flows(user_id):
    from state.expense_session import pop_session as pop_expense
    from state.shopping_session import pop_session as pop_shopping
    from state.settings_session import pop_session as pop_settings
    from state.saved_expense_actions import finalize_saved_expense_action
    pop_expense(user_id)
    pop_shopping(user_id)
    pop_settings(user_id)
    finalize_saved_expense_action(user_id)


def _snapshot(plan):
    return {key: getattr(plan, key) for key in ('title', 'category', 'subcategory', 'amount', 'due_date', 'comment')}


def _description(values):
    amount = format_money_exact(values['amount']) if values.get('amount') else 'пока неизвестна'
    due = values.get('due_date') or 'без даты'
    return '\n'.join([escape(values.get('title', '')), f"{escape(values.get('category', ''))} → {escape(values.get('subcategory', ''))}",
                      f'Сумма: {amount}', f'Дата оплаты: {due}',
                      *([escape(values['comment'])] if values.get('comment') else [])])


async def _failure(message, error):
    if isinstance(error, ValueError):
        await message.answer(escape(str(error)))
    else:
        logging.exception('Ошибка работы с будущими тратами')
        await message.answer('Не удалось проверить или сохранить платёж. Повторите действие; сохранённый платёж не будет добавлен второй раз.')


async def _list(message, session):
    records = await run_blocking(plans.list_plans, history=session.history)
    session.page = min(session.page, max(0, (len(records) - 1) // PAGE_SIZE))
    shown = records[session.page * PAGE_SIZE:(session.page + 1) * PAGE_SIZE]
    session.options = tuple(p.planned_id for p in shown)
    advance(session, 'list')
    choices = []
    for i, plan in enumerate(shown):
        prefix = '⚠️ ' if plan.status == 'pending' and plan.due_date and plan.due_date < plans.today().isoformat() else ''
        choices.append((f"{prefix}{plan.title[:45]} · {plan.due_date or 'без даты'}", f'item{i}'))
    if session.page:
        choices.append(('← Назад', 'prev'))
    if (session.page + 1) * PAGE_SIZE < len(records):
        choices.append(('Далее →', 'next'))
    choices += [('Добавить', 'new'), ('Ожидают оплаты' if session.history else 'История', 'history')]
    from services.planned_reminders import subscription_enabled
    enabled = await run_blocking(subscription_enabled, session.owner_id)
    choices.append(('🔔 Напоминания: включены' if enabled else '🔕 Напоминания: выключены', 'reminders'))
    await message.answer(('История будущих трат' if session.history else '📅 Будущие траты')
                         + (f' · страница {session.page + 1}' if records else '\nПока пусто.'), reply_markup=actions(session, choices))


async def _card(message, session, planned_id):
    plan = await run_blocking(plans.get_plan, planned_id)
    session.record = plan
    session.values = _snapshot(plan)
    advance(session, 'card')
    text = _description(session.values)
    choices = [('К списку', 'list')]
    if plan.status == 'pending':
        choices = [('Оплачено', 'pay'), ('Изменить', 'edit'), ('Отменить платёж', 'cancel')] + choices
    elif plan.status == 'paid':
        text += f'\n\n✅ Оплачено: {format_money_exact(plan.actual_amount)} · {plan.actual_date}\nЗаписал: {escape(plan.paid_by)}\nID фактической траты: <code>{escape(plan.expense_id)}</code>'
    elif plan.status == 'processing':
        text += '\n\n⏳ Проверяем результат оплаты. Повторная запись заблокирована до выяснения результата. Если статус не меняется, обратитесь к оператору.'
        choices = [('Проверить результат', 'backcard')] + choices
    else:
        text += '\n\nОтменено'
    await message.answer(text, reply_markup=actions(session, choices))


async def _preview(message, session):
    advance(session, 'preview')
    await message.answer('Проверьте будущую трату:\n\n' + _description(session.values),
                         reply_markup=actions(session, [('Сохранить', 'save'), ('Изменить', 'edit')]))


async def _categories(message, session):
    _, categories = await run_blocking(get_budget_limits)
    session.options = tuple(categories)
    advance(session, 'category')
    await message.answer('Выберите категорию.' if categories else 'Активных категорий нет. Создайте категорию в настройках.',
                         reply_markup=actions(session, [(v, f'cat{i}') for i, v in enumerate(categories)]))


async def _prompt(message, session, step):
    advance(session, step)
    prompts = {'title': 'Введите название платежа (до 120 символов).',
               'amount': 'Введите плановую сумму или выберите «Пока неизвестна».',
               'due_date': 'Введите дату оплаты ДД.ММ.ГГГГ или выберите «Без даты».',
               'comment': 'Введите комментарий (до 500 символов) или пропустите.'}
    choice = {'amount': [('Пока неизвестна', 'skip')], 'due_date': [('Без даты', 'skip')], 'comment': [('Без комментария', 'skip')]}
    await message.answer(prompts[step], reply_markup=actions(session, choice.get(step, [])))


async def _accept_value(message, session, value):
    step = session.step
    if step == 'title':
        value = plans.validate_text(value, 'Название')
    elif step == 'amount':
        value = plans.parse_amount(value) if value else ''
    elif step == 'due_date':
        value = plans.parse_date(value, optional=True)
    elif step == 'comment':
        if len(value) > 500:
            raise ValueError('Комментарий: не больше 500 символов.')
    session.values[step] = value
    if session.editing:
        await _preview(message, session)
    elif step == 'title':
        await _categories(message, session)
    elif step == 'amount':
        await _prompt(message, session, 'due_date')
    elif step == 'due_date':
        await _prompt(message, session, 'comment')
    elif step == 'comment':
        await _preview(message, session)


@router.message(lambda m: m.text in {'📅 Будущие траты', MENU_PLANNED_TEXT, '/planned'})
async def open_planned(message: types.Message):
    if not await check_access_message(message):
        return
    if not PLANNED_EXPENSES_ENABLED:
        await message.answer('Будущие траты выключены для этого бота.')
        return
    clear_other_flows(message.from_user.id)
    session = create_session(message.from_user.id, message.chat.id)
    try:
        await _list(message, session)
    except Exception as error:
        await _failure(message, error)


@router.callback_query(lambda c: bool(c.data and c.data.startswith('fut:')))
async def planned_callback(callback: types.CallbackQuery):
    if not await check_access_callback(callback):
        return
    if not PLANNED_EXPENSES_ENABLED:
        await callback.answer('Будущие траты выключены.', show_alert=True)
        return
    if callback.message is None:
        await callback.answer('Откройте список платежей заново.', show_alert=True)
        return
    parts = callback.data.split(':')
    if len(parts) != 3:
        await callback.answer('Некорректная кнопка.', show_alert=True)
        return
    user_id, message = callback.from_user.id, callback.message
    if parts[1] == 'open':
        await callback.answer()
        # Reminders are personal; do not expose a budget card in a group chat.
        if message.chat.type != 'private':
            await message.answer('Откройте будущие траты в личном чате с ботом.')
            return
        clear_other_flows(user_id)
        session = create_session(user_id, message.chat.id)
        try:
            await _card(message, session, parts[2])
        except Exception as error:
            await _failure(message, error)
        return
    session = get_session(user_id)
    if session is None or session.token != parts[1] or session.chat_id != message.chat.id:
        await callback.answer('Кнопка устарела. Откройте будущие траты заново.', show_alert=True)
        return
    await callback.answer()
    action = parts[2]
    try:
        if action == 'close':
            pop_session(user_id)
            await message.answer('Будущие траты закрыты.', reply_markup=build_main_menu())
        elif action == 'list':
            await _list(message, session)
        elif action == 'new':
            session = create_session(user_id, message.chat.id)
            await _prompt(message, session, 'title')
        elif action == 'history' and session.step == 'list':
            session.history, session.page = not session.history, 0
            await _list(message, session)
        elif action == 'reminders' and session.step == 'list':
            from services.planned_reminders import subscription_enabled, set_subscription
            enabled = await run_blocking(subscription_enabled, user_id)
            await run_blocking(set_subscription, user_id, not enabled)
            await _list(message, session)
        elif action in {'next', 'prev'} and session.step == 'list':
            session.page = max(0, session.page + (1 if action == 'next' else -1))
            await _list(message, session)
        elif action.startswith('item') and session.step == 'list':
            await _card(message, session, session.options[_index(action, 'item', session.options)])
        elif action.startswith('cat') and session.step == 'category':
            session.values['category'] = session.options[_index(action, 'cat', session.options)]
            session.options = tuple(await run_blocking(get_subcategories_for_category, session.values['category']))
            advance(session, 'subcategory')
            await message.answer('Выберите подкатегорию.', reply_markup=actions(session, [(v, f'sub{i}') for i, v in enumerate(session.options)]))
        elif action.startswith('sub') and session.step == 'subcategory':
            session.values['subcategory'] = session.options[_index(action, 'sub', session.options)]
            if session.editing:
                await _preview(message, session)
            else:
                await _prompt(message, session, 'amount')
        elif action == 'skip' and session.step in {'amount', 'due_date', 'comment'}:
            await _accept_value(message, session, '')
        elif action == 'edit' and session.step in {'card', 'preview'}:
            session.editing = True
            advance(session, 'edit')
            await message.answer('Что изменить?', reply_markup=actions(session, [('Название', 'title'), ('Сумму', 'amount'),
                ('Дату', 'due_date'), ('Категорию', 'category'), ('Комментарий', 'comment')]))
        elif action in {'title', 'amount', 'due_date', 'comment', 'category'} and session.step == 'edit':
            if action == 'category':
                await _categories(message, session)
            else:
                await _prompt(message, session, action)
        elif action == 'save' and session.step == 'preview':
            if session.record:
                plan = await run_blocking(plans.update_plan, session.record.planned_id, session.record.revision, **session.values)
            else:
                plan = await run_blocking(plans.create_plan, planned_id=session.new_id, creator_id=user_id,
                    creator=f'@{callback.from_user.username}' if callback.from_user.username else str(user_id), **session.values)
            await message.answer('Будущая трата сохранена.')
            await _card(message, session, plan.planned_id)
        elif action == 'cancel' and session.step == 'card' and session.record.status == 'pending':
            advance(session, 'cancel')
            await message.answer('Отменить этот платёж?', reply_markup=actions(session, [('Да, отменить', 'cancel_confirm'), ('Вернуться', 'backcard')]))
        elif action == 'backcard' and session.record:
            await _card(message, session, session.record.planned_id)
        elif action == 'cancel_confirm' and session.step == 'cancel':
            plan = await run_blocking(plans.cancel_plan, session.record.planned_id, session.record.revision)
            await _card(message, session, plan.planned_id)
        elif action.startswith('pay'):
            await _payment_action(message, session, action, callback.from_user)
        else:
            raise ValueError('Шаг устарел. Откройте список заново.')
    except Exception as error:
        await _failure(message, error)

        if action == 'pay_confirm' and session.record:
            # A network error can still mean the atomic batch committed. Show
            # the persisted result and its safe check action, never re-append.
            try:
                await _card(message, session, session.record.planned_id)
            except Exception:
                logging.exception('Не удалось проверить сохранённый результат оплаты')


def _index(action, prefix, options):
    raw = action.removeprefix(prefix)
    if not raw.isdigit() or int(raw) >= len(options):
        raise ValueError('Выбор устарел. Откройте список заново.')
    return int(raw)


@router.message(lambda m: bool(PLANNED_EXPENSES_ENABLED and m.from_user and get_session(m.from_user.id)
                               and m.text not in NAVIGATION))
async def planned_text(message: types.Message):
    if not await check_access_message(message):
        return
    session = get_session(message.from_user.id)
    if session is None or session.chat_id != message.chat.id:
        return
    if message.text and message.text.lower() in {'отмена', '/cancel'}:
        pop_session(message.from_user.id)
        await message.answer('Действие отменено.', reply_markup=build_main_menu())
        return
    try:
        if session.step in {'title', 'amount', 'due_date', 'comment'} and message.text:
            await _accept_value(message, session, message.text)
        elif session.step.startswith('pay_') and message.text:
            await _payment_text(message, session)
        else:
            await message.answer('Выберите действие кнопкой или отправьте /cancel.')
    except Exception as error:
        await _failure(message, error)


async def _payment_preview(message, session):
    advance(session, 'pay_preview')
    source = session.values.get('money_source', '')
    await message.answer('Подтвердите оплату:\n\n' + escape(session.record.title)
        + f"\nФактическая сумма: {format_money_exact(session.values['payment_amount'])}"
        + f"\nДата оплаты: {session.values['payment_date']}"
        + (f"\nИсточник: {escape(source)}" if TRACK_MONEY_SOURCE else ''),
        reply_markup=actions(session, [('Подтвердить оплату', 'pay_confirm'), ('Изменить сумму', 'pay_amount'),
                                       ('Изменить дату', 'pay_date'),
                                       *([('Изменить источник', 'pay_source')] if TRACK_MONEY_SOURCE else []),
                                       ('Вернуться к платежу', 'backcard')]))


async def _payment_sources(message, session):
    from services.money_sources import get_money_sources
    session.options = tuple(await run_blocking(get_money_sources))
    advance(session, 'pay_source')
    await message.answer('Выберите источник оплаты.' if session.options else 'Нет активных источников. Добавьте источник в таблицу.',
        reply_markup=actions(session, [(name, f'pay_src{i}') for i, name in enumerate(session.options)]))


async def _payment_action(message, session, action, user):
    if action == 'pay' and session.step == 'card' and session.record.status == 'pending':
        current = await run_blocking(plans.get_plan, session.record.planned_id)
        plans._assert_pending(current, session.record.revision)
        session.values['payment_date'] = plans.today().isoformat()
        session.values['payment_amount'] = current.amount
        if not current.amount:
            advance(session, 'pay_amount')
            await message.answer('Введите фактическую сумму оплаты.', reply_markup=actions(session, []))
        elif TRACK_MONEY_SOURCE:
            await _payment_sources(message, session)
        else:
            await _payment_preview(message, session)
    elif action in {'pay_amount', 'pay_date'} and session.step == 'pay_preview':
        advance(session, action)
        await message.answer('Введите фактическую сумму.' if action == 'pay_amount' else 'Введите дату оплаты ДД.ММ.ГГГГ (или «сегодня»).',
                             reply_markup=actions(session, []))
    elif action == 'pay_source' and session.step == 'pay_preview' and TRACK_MONEY_SOURCE:
        await _payment_sources(message, session)
    elif action.startswith('pay_src') and session.step == 'pay_source':
        session.values['money_source'] = session.options[_index(action, 'pay_src', session.options)]
        await _payment_preview(message, session)
    elif action == 'pay_confirm' and session.step == 'pay_preview':
        actor = f'@{user.username}' if user.username else str(user.id)
        paid = await run_blocking(plans.pay_plan, session.record.planned_id, session.record.revision,
            amount=session.values['payment_amount'], payment_date=session.values['payment_date'],
            actor=actor, money_source=session.values.get('money_source', ''))
        await message.answer('✅ Оплата подтверждена. Фактическая трата записана.')
        await _card(message, session, paid.planned_id)
    else:
        raise ValueError('Шаг оплаты устарел. Откройте карточку заново.')


async def _payment_text(message, session):
    if session.step == 'pay_amount':
        session.values['payment_amount'] = plans.parse_amount(message.text)
        if TRACK_MONEY_SOURCE and not session.values.get('money_source'):
            await _payment_sources(message, session)
        else:
            await _payment_preview(message, session)
    elif session.step == 'pay_date':
        session.values['payment_date'] = plans.parse_date(message.text, payment=True)
        await _payment_preview(message, session)
    else:
        await message.answer('Выберите действие кнопкой или отправьте /cancel.')
