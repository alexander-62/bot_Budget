import asyncio
from contextlib import ExitStack
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import config
from aiogram import Bot
from aiogram.types import Message, CallbackQuery, Chat, User, Update
import app
from handlers import settings as handlers
from services import categories, budget, google_sheets, budget_settings
from services.budget_settings import BudgetSettings
from services.settings_middleware import BudgetSettingsMiddleware
from state import settings_session as state
from state.expense_session import create_session as expense_session, get_active_session as expense_active, pop_session as pop_expense
from state.shopping_session import create_session as shopping_session, get_active_session as shopping_active, pop_session as pop_shopping
from test_budget_settings import Sheet, Spreadsheet


class CategoryServiceTests(unittest.TestCase):
    def setUp(self):
        self.ws = Sheet('Категории', [['Категория','Подкатегория','Активно','Порядок'], ['Еда','Кафе','TRUE','5'], ['Архив','Старое','FALSE','6']])
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(categories, 'get_spreadsheet', return_value=Spreadsheet(self.ws)))
        google_sheets.reset_google_sheets_cache()
        self.addCleanup(google_sheets.reset_google_sheets_cache)

    def test_create_category_and_subcategory_uses_raw_append_and_canonical_parent(self):
        with patch.object(categories, 'clear_budget_snapshot_cache') as clear:
            self.assertEqual(categories.create_category('  Здоровье  ', 'Аптека'), ('Здоровье','Аптека'))
            self.assertEqual(categories.create_subcategory(' еДА ', '  Магазины  '), ('Еда','Магазины'))
        self.assertEqual(self.ws.rows[-2:], [['Здоровье','Аптека','TRUE',7], ['Еда','Магазины','TRUE',8]])
        self.assertTrue(all(call[2]['value_input_option'] == 'RAW' for call in self.ws.writes))
        self.assertEqual(clear.call_count, 2)

    def test_duplicate_including_inactive_and_case_or_spacing_is_rejected(self):
        for function, parent, child in [(categories.create_category,' еДА ','Новая'),
                                        (categories.create_category,'АРХИВ','Новая'),
                                        (categories.create_subcategory,'Еда',' кафе '),
                                        (categories.create_subcategory,'Архив','Старое')]:
            with self.subTest(parent=parent,child=child), self.assertRaises(ValueError):
                function(parent,child)
        self.assertFalse(self.ws.writes)

    def test_replay_after_success_does_not_append_twice(self):
        categories.create_category('Новая', 'Первая')
        with self.assertRaises(ValueError):
            categories.create_category('Новая', 'Первая')
        self.assertEqual(len(self.ws.writes), 1)

    def test_names_validate_and_formula_like_text_stays_literal(self):
        for value in ('', ' '*5, 'a'*65, 'one\ntwo', 'a\x00b'):
            with self.assertRaises(ValueError):
                categories.validate_name(value)
        categories.create_category('=1+1', '<Тест>')
        self.assertEqual(self.ws.rows[-1][:2], ['=1+1','<Тест>'])
        from services.expenses import _safe_category_cell
        self.assertEqual(_safe_category_cell('=1+1'), "'=1+1")


class SettingsFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(handlers, 'check_access_message', AsyncMock(return_value=True)))
        self.stack.enter_context(patch.object(handlers, 'check_access_callback', AsyncMock(return_value=True)))
        self.stack.enter_context(patch.object(handlers, 'refresh_runtime_settings', return_value=BudgetSettings()))
        self.writer = self.stack.enter_context(patch.object(handlers, 'set_runtime_setting', return_value=BudgetSettings()))
        self.create = self.stack.enter_context(patch.object(handlers, 'create_category', side_effect=lambda a,b:(a,b)))
        self.sub = self.stack.enter_context(patch.object(handlers, 'create_subcategory', side_effect=lambda a,b:(a,b)))
        self.replies = []
        async def answer(message, text, **kwargs):
            self.replies.append((text, kwargs))
            return message
        self.stack.enter_context(patch.object(Message, 'answer', answer))
        self.callback_answer = self.stack.enter_context(patch.object(CallbackQuery, 'answer', AsyncMock()))
        state.pop_session(101)
        pop_expense(101)
        pop_shopping(101)

    async def asyncTearDown(self):
        state.pop_session(101)
        pop_expense(101)
        pop_shopping(101)

    def message(self, text='', user=101, chat=101):
        return Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=chat,type='private'),
                       from_user=User(id=user,is_bot=False,first_name='Test',username='test'),text=text)

    def callback(self, action, token=None, user=101, chat=101):
        session = state.get_session(101)
        return CallbackQuery(id='test', from_user=self.message(user=user).from_user, chat_instance='test',
                             message=self.message(chat=chat), data=f'cfg:{token or session.token}:{action}')

    async def open(self):
        await handlers.open_settings(self.message('⚙️ Настройки'))

    async def test_category_created_only_after_first_subcategory_and_stale_button_rejected(self):
        await self.open()
        old = state.get_session(101).token
        await handlers.settings_callback(self.callback('new'))
        await handlers.settings_text(self.message('<Здоровье>'))
        self.create.assert_not_called()
        await handlers.settings_text(self.message('Аптека'))
        self.create.assert_called_once_with('<Здоровье>', 'Аптека')
        self.assertTrue(any('&lt;Здоровье&gt;' in t for t,_ in self.replies))
        await handlers.settings_callback(self.callback('new',token=old))
        self.callback_answer.assert_awaited_with('Эта кнопка устарела. Откройте настройки заново.',show_alert=True)

    async def test_subcategory_uses_displayed_parent_even_when_order_changes(self):
        await self.open()
        with patch.object(handlers,'get_budget_limits',return_value=('0',['Еда','Дом'])):
            await handlers.settings_callback(self.callback('sub'))
        await handlers.settings_callback(self.callback('cat1'))
        await handlers.settings_text(self.message('Ремонт'))
        self.sub.assert_called_once_with('Дом','Ремонт')

    async def test_currency_requires_confirmation_and_preserves_expected_old_value(self):
        await self.open()
        await handlers.settings_callback(self.callback('currency'))
        await handlers.settings_callback(self.callback('RUB'))
        self.writer.assert_not_called()
        self.assertIn('Пересчёта по курсу не будет',self.replies[-1][0])
        await handlers.settings_callback(self.callback('confirm'))
        self.writer.assert_called_once_with('currency','RUB',expected='EUR')

    async def test_limits_off_is_explicit_and_never_deletes_limits(self):
        await self.open()
        await handlers.settings_callback(self.callback('limits'))
        await handlers.settings_callback(self.callback('off'))
        self.writer.assert_called_once_with('monthly_limits_enabled','FALSE')

    async def test_cancel_expiry_other_user_and_other_chat_cannot_mutate(self):
        await self.open()
        await handlers.settings_callback(self.callback('new',user=202))
        await handlers.settings_callback(self.callback('new',chat=202))
        self.assertEqual(state.get_session(101).step,'menu')
        await handlers.settings_callback(self.callback('new'))
        await handlers.settings_text(self.message('/cancel'))
        self.assertIsNone(state.get_session(101))
        self.create.assert_not_called()
        await self.open()
        token=state.get_session(101).token
        state.get_session(101).updated_at -= state.TTL_SECONDS + 1
        await handlers.settings_callback(self.callback('new',token=token))
        self.assertIsNone(state.get_session(101))

    async def test_denied_access_never_reads_or_writes_settings(self):
        with patch.object(handlers,'check_access_message',AsyncMock(return_value=False)), patch.object(handlers,'refresh_runtime_settings') as read:
            await handlers.open_settings(self.message('Настройки'))
        read.assert_not_called()
        self.assertIsNone(state.get_session(101))

    async def test_navigation_abandons_other_flows_before_settings_or_expenses_route(self):
        expense_session(101,'enter_amount')
        shopping_session(101,'enter_items')
        await self.open()
        self.assertIsNone(expense_active(101))
        self.assertIsNone(shopping_active(101))
        next_handler=AsyncMock()
        with patch('services.settings_middleware.settings_initialized',return_value=False):
            await BudgetSettingsMiddleware()(next_handler,self.message('💸 Добавить трату'),{})
        self.assertIsNone(state.get_session(101))
        next_handler.assert_awaited_once()

    async def test_cannot_enable_limits_without_valid_optional_sheet(self):
        await self.open()
        await handlers.settings_callback(self.callback('limits'))
        with patch.object(budget_settings, 'validate_limits_sheet', side_effect=ValueError('Лист лимитов отсутствует')):
            await handlers.settings_callback(self.callback('on'))
        self.writer.assert_not_called()
        self.assertEqual(state.get_session(101).step, 'limits')

    async def test_dispatcher_routes_settings_before_other_active_flows(self):
        dp = app.create_dispatcher()
        bot = Bot('123456:TEST_TOKEN')
        try:
            expense_session(101, 'enter_amount')
            with patch('services.settings_middleware.settings_initialized', return_value=False):
                await dp.feed_update(bot, Update(update_id=1, message=self.message('⚙️ Настройки')))
                self.assertIsNone(expense_active(101))
                await dp.feed_update(bot, Update(update_id=2, callback_query=self.callback('new')))
                await dp.feed_update(bot, Update(update_id=3, message=self.message('Здоровье')))
                await dp.feed_update(bot, Update(update_id=4, message=self.message('Аптека')))
            self.create.assert_called_once_with('Здоровье', 'Аптека')
            self.assertEqual(state.get_session(101).step, 'menu')
        finally:
            await dp.fsm.close()
            await bot.session.close()

    async def test_failed_write_keeps_input_step_for_retry(self):
        await self.open()
        await handlers.settings_callback(self.callback('new'))
        await handlers.settings_text(self.message('Здоровье'))
        self.create.side_effect=OSError('offline')
        await handlers.settings_text(self.message('Аптека'))
        self.assertEqual(state.get_session(101).step,'first_subcategory')
        self.assertTrue(any('Не удалось сохранить' in t for t,_ in self.replies))

    async def test_refresh_failure_stops_handler_instead_of_rendering_wrong_currency(self):
        handler=AsyncMock()
        with patch('services.settings_middleware.settings_initialized',return_value=True), patch('services.settings_middleware.refresh_runtime_settings',side_effect=OSError('offline')):
            await BudgetSettingsMiddleware()(handler,self.message('Test'),{})
        handler.assert_not_awaited()


if __name__ == '__main__': unittest.main()
