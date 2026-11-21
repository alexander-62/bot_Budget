from contextlib import ExitStack
from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo
import unittest
from unittest.mock import AsyncMock, Mock, patch

import config

from services import planned_expenses as plans, planned_reminders as reminders, google_sheets
from planned_fakes import Sheet, Spreadsheet
import scheduler


class PlannedReminderTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.ws=Sheet('Будущие_траты',[list(plans.HEADERS)],10)
        self.users=Sheet('Users',[['username','user_id','digest_enabled','last_digest_date','planned_reminders_enabled'],
            ['alice','101','FALSE','',''],['bob','202','TRUE','','FALSE']],20)
        self.book=Spreadsheet(self.ws,self.users)
        google_sheets.reset_google_sheets_cache();self.addCleanup(google_sheets.reset_google_sheets_cache)
        for module in (plans,reminders):
            self.stack.enter_context(patch.object(module,'get_spreadsheet',return_value=self.book))
        self.stack.enter_context(patch.object(config, 'PLANNED_EXPENSES_ENABLED',True))
        self.stack.enter_context(patch.object(plans,'validate_category'))

    def create(self,**kwargs):
        values=dict(title='Платёж',category='Дом',subcategory='Аренда',due_date='',amount='100',comment='',creator_id=101,creator='@alice')
        values.update(kwargs)
        return plans.create_plan(**values)

    def now(self,day='2026-11-20',clock='21:30',tz='Europe/Moscow'):
        return datetime.fromisoformat(day+'T'+clock).replace(tzinfo=ZoneInfo(tz))

    def test_date_buckets_before_due_day_overdue_and_not_future(self):
        self.create(title='Завтра',due_date='2026-11-21')
        self.create(title='Сегодня',due_date='2026-11-20')
        self.create(title='Просрочен',due_date='2026-11-19')
        self.create(title='Позже',due_date='2026-11-22')
        self.assertEqual(reminders.build_reminder_jobs(self.now(clock='21:29')),[])
        jobs=reminders.build_reminder_jobs(self.now())
        self.assertEqual(len(jobs),3)
        self.assertEqual({j.chat_id for j in jobs},{101})
        for job in jobs: reminders.mark_delivered(job)
        self.assertEqual(reminders.build_reminder_jobs(self.now()),[])
        self.assertEqual(len(reminders.build_reminder_jobs(self.now(day='2026-11-21'))),4)

    def test_weekly_undated_groups_by_owner_and_persists_after_restart(self):
        for i in range(10): self.create(title=f'Без даты {i}')
        self.assertEqual(reminders.build_reminder_jobs(self.now()),[])
        monday=self.now(day='2026-11-23')
        jobs=reminders.build_reminder_jobs(monday)
        self.assertEqual([len(j.items) for j in jobs],[8,2])
        for job in jobs: reminders.mark_delivered(job)
        google_sheets.reset_google_sheets_cache()
        self.assertEqual(reminders.build_reminder_jobs(monday),[])
        self.assertEqual(len(reminders.build_reminder_jobs(self.now(day='2026-11-30'))),2)

    def test_subscription_is_independent_from_digest_and_removed_creator_is_excluded(self):
        self.create(creator_id=101,due_date='2026-11-20')
        self.create(creator_id=202,due_date='2026-11-20')
        self.create(creator_id=303,due_date='2026-11-20')
        jobs=reminders.build_reminder_jobs(self.now())
        self.assertEqual([j.chat_id for j in jobs],[101])
        reminders.set_subscription(101,False)
        self.assertEqual(reminders.build_reminder_jobs(self.now()),[])
        self.assertEqual(self.users.rows[1][2],'FALSE')

    def test_snooze_preserves_due_date_and_delivers_once_even_for_undated_items(self):
        plan = self.create(due_date='2026-11-20')
        undated = self.create(title='Без даты')
        with patch.object(plans, 'today', return_value=self.now().date()):
            with self.assertRaises(ValueError):
                plans.snooze_plan(plan.planned_id, plan.revision, 202, '2026-11-22')
            for item in (plan, undated):
                plans.snooze_plan(item.planned_id, item.revision, 101, '2026-11-22')
        self.assertEqual(plans.get_plan(plan.planned_id).due_date, plan.due_date)
        self.assertEqual(reminders.build_reminder_jobs(self.now(day='2026-11-21')), [])
        current = self.now(day='2026-11-23')
        jobs = reminders.build_reminder_jobs(current)
        self.assertEqual(len(jobs), 2)
        for job in jobs:
            reminders.mark_delivered(job)
        self.assertEqual(reminders.build_reminder_jobs(current), [])

    def test_reminder_without_description_uses_subcategory(self):
        plan = self.create(title='', subcategory='Расходники', due_date='2026-11-20')
        job, = reminders.build_reminder_jobs(self.now())
        self.assertEqual(job.items[0][0], plan.planned_id)
        self.assertEqual(job.titles, ('Расходники',))
        self.assertIn('Расходники', job.text)

    def test_timezone_conversion_and_paid_cancelled_processing_exclusion(self):
        p=self.create(due_date='2026-11-20')
        self.assertEqual(reminders.build_reminder_jobs(self.now(clock='18:29',tz='UTC')),[])
        self.assertEqual(len(reminders.build_reminder_jobs(self.now(clock='18:30',tz='UTC'))),1)
        for status in ('paid','cancelled','processing'):
            self.ws.rows[1]=replace(p,status=status).values()
            self.assertEqual(reminders.build_reminder_jobs(self.now()),[])

    def test_delayed_ack_does_not_overwrite_edited_or_paid_plan(self):
        p=self.create(due_date='2026-11-20')
        job=reminders.build_reminder_jobs(self.now())[0]
        newer=plans.update_plan(p.planned_id,p.revision,title='Новое название',category=p.category,subcategory=p.subcategory,due_date=p.due_date)
        reminders.mark_delivered(job)
        self.assertEqual(plans.get_plan(p.planned_id),newer)

    def test_old_users_header_defaults_enabled_without_read_side_migration(self):
        self.users.rows=[row[:4] for row in self.users.rows]
        self.assertTrue(reminders.subscription_enabled(101))
        self.assertEqual(len(self.users.rows[0]),4)
        reminders.set_subscription(101,False)
        self.assertEqual(self.users.rows[0][-1],reminders.SUBSCRIPTION_HEADER)
        self.assertFalse(reminders.subscription_enabled(101))


class PlannedSchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_send_retries_and_only_success_marks_delivered(self):
        job=reminders.ReminderJob(101,'text',(('id','rev','day:2026-11-20'),),('title',))
        bot=Mock(send_message=AsyncMock(side_effect=[RuntimeError('Telegram down'),None]))
        with patch.object(config, 'PLANNED_EXPENSES_ENABLED',True), \
             patch.object(reminders,'build_reminder_jobs',return_value=[job]), \
             patch.object(reminders,'mark_delivered') as mark, \
             patch('services.budget_settings.settings_initialized',return_value=False):
            self.assertEqual(await scheduler.send_due_planned_reminders(bot),0)
            mark.assert_not_called()
            self.assertEqual(await scheduler.send_due_planned_reminders(bot),1)
            mark.assert_called_once_with(job)
            self.assertEqual(bot.send_message.call_args.kwargs['reply_markup'].inline_keyboard[0][0].callback_data,'fut:open:id')

    async def test_disabled_flag_skips_all_io(self):
        with patch.object(config, 'PLANNED_EXPENSES_ENABLED',False),patch.object(reminders,'build_reminder_jobs') as build:
            self.assertEqual(await scheduler.send_due_planned_reminders(Mock()),0)
            build.assert_not_called()

    async def test_digest_failure_does_not_prevent_future_reminders(self):
        import asyncio
        digest=AsyncMock(side_effect=RuntimeError('Sheets digest failure'))
        future=AsyncMock(return_value=0)
        with patch.object(scheduler,'send_due_daily_digests',digest),patch.object(scheduler,'send_due_planned_reminders',future), \
             patch.object(scheduler.asyncio,'sleep',AsyncMock(side_effect=asyncio.CancelledError)):
            with self.assertRaises(asyncio.CancelledError):
                await scheduler.run_daily_digest_scheduler(Mock())
            future.assert_awaited_once()


if __name__=='__main__':unittest.main()
