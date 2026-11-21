from contextlib import ExitStack
from datetime import date, datetime, timezone
import unittest
from unittest.mock import AsyncMock, patch

import config
from aiogram import Bot
from aiogram.types import CallbackQuery, Chat, Message, User, Update
import app
from handlers import planned as flow
from services import planned_expenses as plans, google_sheets, expenses
from state import planned_session as state
from planned_fakes import Sheet, Spreadsheet


def message(text='', user_id=101, chat_id=101):
    return Message(message_id=1, date=datetime.now(timezone.utc),
        chat=Chat(id=chat_id, type='private'), from_user=User(id=user_id,is_bot=False,first_name='User',username='alice'), text=text)


class PlannedFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.replies = []
        self.ws = Sheet('Будущие_траты',[list(plans.HEADERS)],10)
        self.actual = Sheet('Траты_по_месяцам',[['Дата','Месяц','Пользователь','Категория','Подкатегория','Сумма','Комментарий','expense_id']],20)
        self.users = Sheet('Users',[['username','user_id','digest_enabled','last_digest_date'],['alice','101','',''],['bob','202','','']],30)
        self.book = Spreadsheet(self.ws,self.actual,self.users)
        google_sheets.reset_google_sheets_cache()
        self.addCleanup(google_sheets.reset_google_sheets_cache)
        self.addCleanup(state._sessions.clear)
        for module in (plans,expenses,google_sheets):
            self.stack.enter_context(patch.object(module,'get_spreadsheet',return_value=self.book))
        self.stack.enter_context(patch('services.planned_reminders.get_spreadsheet',return_value=self.book))
        self.stack.enter_context(patch.object(config, 'PLANNED_EXPENSES_ENABLED', True))
        self.stack.enter_context(patch.object(plans,'today',return_value=date(2026,11,20)))
        self.stack.enter_context(patch.object(plans,'validate_category'))
        self.stack.enter_context(patch.object(flow,'get_budget_limits',return_value=('0',['Дом'])))
        self.stack.enter_context(patch.object(flow,'get_subcategories_for_category',return_value=['Аренда']))
        self.stack.enter_context(patch.object(flow,'TRACK_MONEY_SOURCE',False))
        self.stack.enter_context(patch.object(config,'TRACK_MONEY_SOURCE',False))
        self.stack.enter_context(patch.object(expenses,'TRACK_MONEY_SOURCE',False))
        self.access_message=self.stack.enter_context(patch.object(flow,'check_access_message',AsyncMock(return_value=True)))
        self.access_callback=self.stack.enter_context(patch.object(flow,'check_access_callback',AsyncMock(return_value=True)))
        self.alert=self.stack.enter_context(patch.object(CallbackQuery,'answer',new_callable=AsyncMock))
        async def answer(target,text,**kwargs):
            self.replies.append((text,kwargs))
            return message(text)
        self.stack.enter_context(patch.object(Message,'answer',answer))

    async def click(self, action, user_id=101, data=None, chat_id=101):
        session=state.get_session(user_id)
        cb=CallbackQuery(id='click',from_user=message(user_id=user_id).from_user,chat_instance='test',
                         message=message(chat_id=chat_id),data=data or f'fut:{session.token}:{action}')
        await flow.planned_callback(cb)
        return cb

    async def text(self,text,user_id=101,chat_id=101):
        await flow.planned_text(message(text,user_id,chat_id))

    async def start_creation(self):
        await flow.open_planned(message('/planned'))
        await self.click('new')
        self.assertEqual(state.get_session(101).step, 'category')
        await self.click('cat0')
        await self.click('sub0')

    async def create(self, amount='', due=''):
        await self.start_creation()
        await (self.text(amount) if amount else self.click('skip'))
        await (self.text(due) if due else self.click('skip'))
        return state.get_session(101).record

    async def test_create_without_date_or_amount_then_pay_with_actual_details(self):
        p=await self.create()
        self.assertEqual(p.amount,'')
        await self.click('pay')
        self.assertEqual(state.get_session(101).step,'pay_amount')
        await self.text('800,25')
        await self.click('pay_date')
        await self.text('31.10.2026')
        await self.click('pay_confirm')
        self.assertEqual(plans.get_plan(p.planned_id).actual_date,'2026-10-31')
        self.assertEqual(len(self.actual.rows),2)
        self.assertTrue(any('Фактическая трата записана' in text for text,_ in self.replies))

    async def test_description_on_amount_line_is_used_once_on_payment(self):
        p = await self.create('74 000 2 головы латекс', '27.11.2026')
        self.assertEqual((p.amount, p.title, p.comment, p.due_date),
                         ('74000,00', '2 головы латекс', '', '2026-11-27'))
        self.assertIn('Будущая трата сохранена', self.replies[-1][0])
        self.assertEqual(len(self.actual.rows), 1)
        await self.click('pay')
        await self.click('pay_confirm')
        self.assertEqual(self.actual.rows[1][6], '2 головы латекс')

    async def test_description_only_tomorrow_and_stale_skip_do_not_save_twice(self):
        await self.start_creation()
        await self.click('description')
        await self.text('Месячная аренда')
        old_callback = self.callback_data('skip')
        await self.click('date_tomorrow')
        plan = state.get_session(101).record
        self.assertEqual((plan.amount, plan.title, plan.due_date), ('', 'Месячная аренда', '2026-11-21'))
        await self.click('', data=old_callback)
        self.assertIn('устарела', self.alert.call_args.args[0])
        self.assertEqual(len(plans.list_plans()), 1)

    def callback_data(self, action):
        return f'fut:{state.get_session(101).token}:{action}'

    async def test_amount_only_shows_subcategory_as_name(self):
        plan = await self.create('120')
        self.assertEqual(plan.display_title, 'Аренда')
        self.assertEqual(plan.title, '')
        await self.click('pay')
        await self.click('pay_confirm')
        self.assertEqual(self.actual.rows[1][6], '')

    async def test_create_retry_reopens_saved_card_after_lost_response(self):
        await self.start_creation()
        await self.text('100 Аренда')
        self.book.batch_error_after = True
        with self.assertLogs(level='ERROR'):
            await self.click('skip')
        self.assertEqual(state.get_session(101).step, 'create_retry')
        await self.click('create_retry')
        self.assertEqual(state.get_session(101).step, 'card')
        self.assertEqual(len(plans.list_plans()), 1)

    async def test_old_additional_comment_survives_editing_amount(self):
        plan = plans.create_plan(creator_id=101, creator='@alice', title='Аренда',
                                 category='Дом', subcategory='Аренда', comment='По договору')
        await self.click('', data=f'fut:open:{plan.planned_id}')
        self.assertIn('По договору', self.replies[-1][0])
        await self.click('edit')
        self.assertIn('Дополнительный комментарий',
                      [row[0].text for row in self.replies[-1][1]['reply_markup'].inline_keyboard])
        await self.click('amount')
        await self.text('100')
        await self.click('save')
        self.assertEqual(plans.get_plan(plan.planned_id).comment, 'По договору')

    async def test_edit_cancel_history_and_stale_callback(self):
        p=await self.create('100','2026-11-21')
        old_token=state.get_session(101).token
        await self.click('edit')
        await self.click('amount')
        await self.text('120,50')
        await self.click('save')
        self.assertEqual(plans.get_plan(p.planned_id).amount,'120,50')
        await self.click('cancel',data=f'fut:{old_token}:cancel')
        self.assertEqual(plans.get_plan(p.planned_id).status,'pending')
        self.assertIn('устарела',self.alert.call_args.args[0])
        await self.click('cancel')
        await self.click('cancel_confirm')
        self.assertEqual(plans.get_plan(p.planned_id).status,'cancelled')
        await self.click('list')
        await self.click('history')
        self.assertEqual(len(state.get_session(101).options),1)

    async def test_subscription_toggle_is_separate_from_daily_digest(self):
        await flow.open_planned(message('/planned'))
        await self.click('reminders')
        self.assertEqual(self.users.rows[0][-1],'planned_reminders_enabled')
        self.assertEqual(self.users.rows[1][-1],'FALSE')
        self.assertEqual(self.users.rows[1][2],'')

    async def test_reminder_opens_after_session_restart_for_another_allowed_member(self):
        p=await self.create('100')
        state._sessions.clear()
        await self.click('',user_id=202,chat_id=202,data=f'fut:open:{p.planned_id}')
        self.assertEqual(state.get_session(202).record.planned_id,p.planned_id)
        await self.click('pay',user_id=202,chat_id=202)
        await self.click('pay_confirm',user_id=202,chat_id=202)
        self.assertEqual(len(self.actual.rows),2)

    async def test_access_flag_wrong_chat_and_expired_session_do_not_write(self):
        await flow.open_planned(message('/planned'))
        token=state.get_session(101).token
        await self.click('new',chat_id=404)
        self.assertEqual(state.get_session(101).step,'list')
        state.get_session(101).updated_at-=1000
        await self.click('',data=f'fut:{token}:new')
        self.assertIn('устарела',self.alert.call_args.args[0])
        self.access_callback.return_value=False
        await self.click('',data='fut:open:unknown')
        self.assertEqual(len(self.ws.rows),1)
        with patch.object(config, 'PLANNED_EXPENSES_ENABLED',False):
            self.access_callback.return_value=True
            await self.click('',data='fut:open:unknown')
            self.assertIn('выключены',self.alert.call_args.args[0])

    async def test_source_is_required_and_revalidated_at_payment(self):
        p=await self.create('100')
        with patch.object(flow,'TRACK_MONEY_SOURCE',True),patch.object(config,'TRACK_MONEY_SOURCE',True),patch.object(expenses,'TRACK_MONEY_SOURCE',True), \
             patch('services.money_sources.get_money_sources',return_value=['Карта']), \
             patch('services.money_sources.validate_money_source',side_effect=ValueError('Источник больше не активен')):
            await self.click('pay')
            self.assertEqual(state.get_session(101).step,'pay_source')
            await self.click('pay_src0')
            await self.click('pay_confirm')
            self.assertEqual(plans.get_plan(p.planned_id).status,'pending')
            self.assertEqual(len(self.actual.rows),1)


    async def test_lost_payment_response_shows_persisted_status_instead_of_second_write(self):
        p=await self.create('100')
        await self.click('pay')
        self.book.batch_error_after=True
        await self.click('pay_confirm')
        self.assertEqual(state.get_session(101).record.status,'paid')
        self.assertEqual(len(self.actual.rows),2)
        self.assertTrue(any('ID фактической траты' in text for text,_ in self.replies))

    async def test_pagination_does_not_hide_more_than_one_page_of_plans(self):
        for i in range(10):
            plans.create_plan(creator_id=101,creator='@alice',title=f'Платёж {i}',category='Дом',subcategory='Аренда')
        await flow.open_planned(message('/planned'))
        self.assertEqual(len(state.get_session(101).options),8)
        await self.click('next')
        self.assertEqual(len(state.get_session(101).options),2)
        await self.click('prev')
        self.assertEqual(len(state.get_session(101).options),8)

    async def test_snooze_repeat_forecast_and_payment_correction_buttons(self):
        plan = await self.create('100', '2026-11-21')
        await self.click('snooze')
        await self.click('custom')
        await self.text('25.11.2026')
        self.assertEqual(state.get_session(101).record.remind_on, '2026-11-25')
        await self.click('repeat')
        await self.click('weekly')
        self.assertEqual(state.get_session(101).record.repeat_rule, 'weekly')
        await self.click('list')
        await self.click('forecast')
        self.assertIn('Прогноз будущих трат', self.replies[-1][0])
        await self.click('', data=f'fut:open:{plan.planned_id}')
        await self.click('pay')
        await self.click('pay_confirm')
        await self.click('correct')
        await self.click('cor_amount')
        await self.text('99,25')
        await self.click('cor_confirm')
        self.assertEqual(state.get_session(101).record.actual_amount, '99,25')
        await self.click('undo')
        await self.click('undo_confirm')
        self.assertEqual(state.get_session(101).record.status, 'pending')
        self.assertEqual(self.actual.rows[1], [''] * 8)

    async def test_real_dispatcher_navigates_from_old_flow_and_back_to_settings(self):
        from state.expense_session import create_session as expense_session, get_active_session
        from state.settings_session import get_session as settings_session
        from handlers import settings
        from services.budget_settings import BudgetSettings
        expense_session(101,'enter_amount')
        bot=Bot('123456:TEST_TOKEN')
        dp=app.create_dispatcher()
        with patch.object(settings,'check_access_message',AsyncMock(return_value=True)), \
             patch.object(settings,'refresh_runtime_settings',return_value=BudgetSettings()):
            try:
                await dp.feed_update(bot,Update(update_id=1,message=message('/planned')))
                self.assertIsNone(get_active_session(101))
                self.assertIsNotNone(state.get_session(101))
                await dp.feed_update(bot,Update(update_id=2,message=message('⚙️ Настройки')))
                self.assertIsNone(state.get_session(101))
                self.assertIsNotNone(settings_session(101))
            finally:
                from state.settings_session import pop_session
                pop_session(101)
                await dp.fsm.close()
                await bot.session.close()


if __name__=='__main__':
    unittest.main()
