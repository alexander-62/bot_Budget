from contextlib import ExitStack
from dataclasses import replace
from datetime import date, datetime, timezone
from itertools import count
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import config
from aiogram import Bot, methods, types
from aiogram.exceptions import TelegramBadRequest

import app
from handlers import expenses, menu, planned, settings, shopping
from keyboards.planned import open_plan_keyboard
from services.budget_settings import BudgetSettings
from services.expenses import SavedExpense
from services.planned_expenses import PlannedExpense
from services.settings_middleware import abandon_sessions
from state import dialog_messages


class TelegramDialogTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.dialogs = dialog_messages.DialogMessagesMiddleware()
        with patch.object(dialog_messages, 'DialogMessagesMiddleware', return_value=cls.dialogs):
            cls.dp = app.create_dispatcher()

    async def asyncSetUp(self):
        self.dialogs.messages.clear()
        self.bot = Bot('123456:TEST_TOKEN')
        self.addAsyncCleanup(self.dp.fsm.close)
        self.addAsyncCleanup(self.bot.session.close)
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.addCleanup(abandon_sessions, 101)
        self.addCleanup(abandon_sessions, 202)
        stack.enter_context(patch.object(Bot, '__call__', self.telegram_api))
        stack.enter_context(patch('services.access.is_allowed_user', return_value=(True, '')))
        stack.enter_context(patch('services.access.sync_allowed_user_chat_id'))
        stack.enter_context(patch('services.settings_middleware.settings_initialized', return_value=False))
        stack.enter_context(patch.object(config, 'PLANNED_EXPENSES_ENABLED', True))
        stack.enter_context(patch.object(expenses, 'TRACK_MONEY_SOURCE', False))
        stack.enter_context(patch.object(planned, 'TRACK_MONEY_SOURCE', False))
        for module in (expenses, planned, settings):
            stack.enter_context(patch.object(module, 'get_budget_limits', return_value=('0', ['Дом'])))
        for module in (expenses, planned):
            stack.enter_context(patch.object(module, 'get_subcategories_for_category', return_value=['Аренда']))
        stack.enter_context(patch.object(expenses, 'is_allowed_username', return_value=(True, '')))
        stack.enter_context(patch.object(expenses, 'is_allowed_user', return_value=(True, '')))
        stack.enter_context(patch.object(expenses, 'get_category_details', return_value=('Дом', '0', '120', '-120', [])))
        self.write_expense = stack.enter_context(patch.object(expenses, 'write_expense', side_effect=self.saved_expense))
        stack.enter_context(patch.object(settings, 'refresh_runtime_settings', return_value=BudgetSettings()))
        self.create_category = stack.enter_context(patch.object(settings, 'create_category', side_effect=lambda a, b: (a, b)))
        stack.enter_context(patch.object(shopping, 'get_shopping_items', return_value=['Рис']))
        self.add_items = stack.enter_context(patch.object(shopping, 'add_shopping_items', return_value=(['Молоко'], ['Рис'])))
        stack.enter_context(patch.object(menu, 'get_report_categories', return_value=['Дом']))
        stack.enter_context(patch.object(menu, 'get_month_totals', return_value=('0', '120', '-120')))
        stack.enter_context(patch.object(menu, 'get_category_details', return_value=('Дом', '0', '120', '-120', [])))
        stack.enter_context(patch('services.planned_reminders.subscription_enabled', return_value=True))
        stack.enter_context(patch.object(planned.plans, 'today', return_value=date(2026, 11, 21)))
        self.create_plan = stack.enter_context(patch.object(planned.plans, 'create_plan', side_effect=self.save_plan))
        self.pay_plan = stack.enter_context(patch.object(planned.plans, 'pay_plan', side_effect=self.pay))
        stack.enter_context(patch.object(planned.plans, 'list_plans', side_effect=lambda **kwargs: list(self.plans.values())))
        stack.enter_context(patch.object(planned.plans, 'get_plan', side_effect=lambda record_id: self.plans[record_id]))
        self.ids = count(1000)
        self.plans = {}
        self.chat_messages = {}
        self.user_messages = set()
        self.alerts = []
        self.reject_deletion = set()
        self.reject_edit = set()

    @staticmethod
    def saved_expense(**kwargs):
        return SavedExpense('expense-1', 'Траты', 2, 'A2:H2', '2026-11-21', '2026-11', **kwargs)

    def save_plan(self, *, creator_id, **values):
        plan = PlannedExpense(**values, creator_id=str(creator_id), comment='', revision='original')
        self.plans[plan.planned_id] = plan
        return plan

    def pay(self, planned_id, revision, *, amount, payment_date, actor, **values):
        plan = replace(self.plans[planned_id], status='paid', revision='paid',
                       actual_amount=amount, actual_date=payment_date, paid_by=actor, expense_id='expense-1')
        self.plans[planned_id] = plan
        return plan

    def message(self, chat_id, text, *, is_bot=False, markup=None):
        return types.Message(
            message_id=next(self.ids), chat=types.Chat(id=chat_id, type='private'),
            date=datetime.now(timezone.utc), text=text, reply_markup=markup,
            from_user=types.User(id=self.bot.id if is_bot else chat_id, is_bot=is_bot, first_name='Test'),
        )

    async def telegram_api(self, method, **kwargs):
        if isinstance(method, methods.SendMessage):
            markup = method.reply_markup if isinstance(method.reply_markup, types.InlineKeyboardMarkup) else None
            message = self.message(method.chat_id, method.text, is_bot=True, markup=markup)
            self.chat_messages[message.message_id] = message
            return message
        if isinstance(method, methods.AnswerCallbackQuery):
            self.alerts.append(method.text)
            return True
        if isinstance(method, methods.DeleteMessage):
            self.assertNotIn(method.message_id, self.user_messages)
            if method.message_id in self.reject_deletion:
                raise TelegramBadRequest(method, 'message cannot be deleted')
            del self.chat_messages[method.message_id]
            return True
        if isinstance(method, (methods.EditMessageText, methods.EditMessageReplyMarkup)):
            self.assertNotIn(method.message_id, self.user_messages)
            if isinstance(method, methods.EditMessageText) and method.message_id in self.reject_edit:
                raise TelegramBadRequest(method, 'message cannot be edited')
            message = self.chat_messages[method.message_id]
            self.assertEqual(message.chat.id, method.chat_id)
            fields = {'reply_markup': method.reply_markup}
            if isinstance(method, methods.EditMessageText):
                fields['text'] = method.text
            message = message.model_copy(update=fields)
            self.chat_messages[method.message_id] = message
            return message
        raise AssertionError(f'Unexpected Telegram method {type(method).__name__}')

    async def text(self, text, user_id=101):
        message = self.message(user_id, text)
        self.user_messages.add(message.message_id)
        await self.dp.feed_update(self.bot, types.Update(update_id=next(self.ids), message=message))

    async def click(self, message, label=None, *, data=None, user_id=101):
        if data is None:
            data = next(button.callback_data for row in message.reply_markup.inline_keyboard
                        for button in row if button.text == label)
        query = types.CallbackQuery(id=str(next(self.ids)), chat_instance='test', message=message,
                                    from_user=self.message(user_id, '').from_user, data=data)
        await self.dp.feed_update(self.bot, types.Update(update_id=next(self.ids), callback_query=query))

    def latest(self):
        return self.chat_messages[next(reversed(self.chat_messages))]

    def labels(self, message):
        return [button.text for row in message.reply_markup.inline_keyboard for button in row]

    async def test_plan_creation_payment_and_reminder_keep_only_useful_cards(self):
        await self.text('/planned')
        original = self.latest().message_id
        for label in ('Добавить', 'Дом', 'Аренда'):
            await self.click(self.latest(), label)
            self.assertEqual(set(self.chat_messages), {original})
        await self.text('не сумма')
        invalid = self.latest()
        self.assertIn('Введите сумму', invalid.text)
        self.assertIn('Без суммы и описания', self.labels(invalid))
        await self.text('74 000 Головы латекс')
        self.assertNotIn(invalid.message_id, self.chat_messages)
        date_prompt = self.latest()
        await self.click(date_prompt, 'Без даты')
        created = self.latest()
        self.assertEqual(created.message_id, date_prompt.message_id)
        self.assertIn('Будущая трата сохранена', created.text)
        self.create_plan.assert_called_once()
        self.assertEqual(self.create_plan.call_args.kwargs['title'], 'Головы латекс')
        self.assertNotIn('comment', self.create_plan.call_args.kwargs)
        await self.click(created, 'Оплачено')
        self.assertEqual(self.labels(self.chat_messages[created.message_id]), ['Открыть платёж'])
        preview = self.latest()
        await self.click(preview, 'Подтвердить оплату')
        self.pay_plan.assert_called_once()
        paid = self.latest()
        self.assertEqual(paid.message_id, preview.message_id)
        self.assertIn('Фактическая трата записана', paid.text)
        await self.click(paid, 'К списку')
        listing = self.latest()
        await self.click(listing, 'Закрыть')
        self.assertEqual(set(self.chat_messages), {created.message_id, paid.message_id})
        record_id = next(iter(self.plans))
        reminder = self.message(101, 'Напоминание', is_bot=True, markup=open_plan_keyboard(record_id))
        self.chat_messages[reminder.message_id] = reminder
        await self.click(reminder, 'Открыть платёж')
        self.assertIn('Оплачено', self.latest().text)
        await self.text('/cancel')
        self.assertEqual(self.chat_messages[reminder.message_id], reminder)
        self.assertEqual(len(self.chat_messages), 3)

    async def test_regular_expense_validation_and_navigation_retire_old_action_buttons(self):
        await self.text('💸 Добавить трату')
        await self.click(self.latest(), 'Дом')
        await self.click(self.latest(), 'Аренда')
        await self.text('ошибка')
        self.assertIn('Некорректная сумма', self.latest().text)
        await self.text('снова ошибка')
        self.assertEqual(self.latest().text.count('Некорректная сумма'), 1)
        self.assertEqual(len(self.chat_messages), 1)
        await self.text('120 Аренда <дома>')
        receipt = self.latest()
        self.assertIn('Аренда &lt;дома&gt;', receipt.text)
        self.assertEqual(len(self.chat_messages), 1)
        self.write_expense.assert_called_once()
        await self.text('⚙️ Настройки')
        self.assertIsNone(self.chat_messages[receipt.message_id].reply_markup)
        await self.text('/cancel')
        self.assertEqual(set(self.chat_messages), {receipt.message_id})

    async def test_shopping_settings_and_monthly_report(self):
        await self.text('🛒 Список Покупок')
        shopping_list = self.latest()
        await self.click(shopping_list, 'Добавить')
        self.assertEqual(self.latest().message_id, shopping_list.message_id)
        await self.text('Молоко, Рис')
        self.add_items.assert_called_once_with(['Молоко', 'Рис'])
        added, shopping_list = self.chat_messages.values()
        self.assertIn('Уже в списке', added.text)
        await self.text('⚙️ Настройки')
        self.assertNotIn(shopping_list.message_id, self.chat_messages)
        await self.click(self.latest(), '➕ Создать категорию')
        await self.text('Здоровье')
        await self.text('Аптека')
        self.create_category.assert_called_once_with('Здоровье', 'Аптека')
        await self.text('📊 Расходы за месяц')
        report = self.latest()
        await self.click(report, 'Дом')
        self.assertEqual(self.latest().message_id, report.message_id)
        await self.click(report, 'Дом')  # replay the category button after it was replaced
        self.assertIn('устарел', self.alerts[-1])
        await self.click(self.latest(), 'К отчёту')
        await self.click(self.latest(), 'Закрыть')
        self.assertEqual(len(self.chat_messages), 2)
        self.assertIn('Здоровье → Аптека', self.latest().text)

    async def test_failed_edit_or_delete_leaves_no_unused_controls_and_respects_owner(self):
        await self.text('📊 Расходы за месяц')
        report = self.latest()
        await self.text('⚙️ Настройки', user_id=202)
        other = self.latest()
        self.reject_edit.add(report.message_id)
        self.reject_deletion.add(report.message_id)
        await self.click(report, 'Дом')
        details = self.latest()
        self.assertNotEqual(details.message_id, report.message_id)
        self.assertIsNone(self.chat_messages[report.message_id].reply_markup)
        await self.click(details, 'Закрыть')
        self.assertEqual(set(self.chat_messages), {report.message_id, other.message_id})

    async def test_restart_confirmation_is_the_only_startup_message_for_requester(self):
        with TemporaryDirectory() as directory:
            notice = Path(directory) / '.restart_notice.json'
            with (patch.object(menu, 'RESTART_NOTICE_FILE', notice),
                  patch.object(app, 'RESTART_NOTICE_FILE', notice),
                  patch.object(app, 'get_allowed_chat_ids', return_value=[101, 202])):
                menu._write_restart_notice(101, 'test', updated=True)
                requester = await app.notify_restart_complete(self.bot)
                await app.notify_startup(self.bot, skip_chat_id=requester)
            self.assertFalse(notice.exists())
        first, second = self.chat_messages.values()
        self.assertEqual((first.chat.id, second.chat.id), (101, 202))
        self.assertIn('Обновление установлено. Бот снова запущен.', first.text)
        self.assertIn('Бот запущен.', second.text)

    async def test_expired_dialog_is_removed_on_next_update(self):
        with patch.object(dialog_messages, 'monotonic', return_value=10):
            await self.text('🛒 Список Покупок')
        shopping_list = self.latest()
        with patch.object(dialog_messages, 'monotonic', return_value=10 + dialog_messages.STEP_TIMEOUT):
            await self.text('/cancel')
        self.assertNotIn(shopping_list.message_id, self.chat_messages)


if __name__ == '__main__':
    unittest.main()
