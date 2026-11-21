from contextlib import ExitStack
from dataclasses import replace
from datetime import date
import unittest
from unittest.mock import patch

import config
from services import planned_expenses as plans, google_sheets, expenses, budget
from planned_fakes import Sheet, Spreadsheet


class PlannedFixture:
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.ws = Sheet('Будущие_траты', [list(plans.HEADERS)], 10)
        self.expenses = Sheet('Траты_по_месяцам', [['Дата','Месяц','Пользователь','Категория','Подкатегория','Сумма','Комментарий','expense_id']], 20)
        self.book = Spreadsheet(self.ws, self.expenses)
        google_sheets.reset_google_sheets_cache()
        self.addCleanup(google_sheets.reset_google_sheets_cache)
        for module in (plans, expenses):
            self.stack.enter_context(patch.object(module, 'get_spreadsheet', return_value=self.book))
        self.stack.enter_context(patch.object(config, 'PLANNED_EXPENSES_ENABLED', True))
        self.stack.enter_context(patch.object(plans, 'today', return_value=date(2026,11,20)))
        self.stack.enter_context(patch.object(plans, 'validate_category'))
        self.stack.enter_context(patch.object(config, 'TRACK_MONEY_SOURCE', False))
        self.stack.enter_context(patch.object(expenses, 'TRACK_MONEY_SOURCE', False))

    def create(self, **kwargs):
        values = dict(title='Страховка', category='Авто', subcategory='Страхование', amount='', due_date='', comment='')
        values.update(kwargs)
        return plans.create_plan(creator_id=101, creator='@alice', **values)


class PlannedExpensesTests(PlannedFixture, unittest.TestCase):
    def test_optional_fields_persist_and_have_no_effect_on_actual_totals(self):
        p = self.create()
        self.assertEqual(plans.get_plan(p.planned_id), p)
        self.assertEqual(p.amount, '')
        self.assertEqual(p.due_date, '')
        self.assertEqual(len(self.expenses.rows), 1)
        self.assertEqual(plans.list_plans(), [p])

    def test_raw_text_formula_and_sort_history(self):
        undated = self.create(title='=FORMULA()')
        future = self.create(due_date='21.11.2026', amount='120,50')
        overdue = self.create(due_date='19.11.2026')
        self.assertEqual([p.planned_id for p in plans.list_plans()], [overdue.planned_id, future.planned_id, undated.planned_id])
        cancelled = plans.cancel_plan(overdue.planned_id, overdue.revision)
        self.assertEqual(plans.list_plans(history=True), [cancelled])
        self.assertEqual(self.ws.writes[0][2]['value_input_option'], 'RAW')

    def test_revision_rejects_stale_edit_and_cancel_after_row_moves(self):
        p = self.create()
        self.ws.rows.insert(1, [''])
        updated = plans.update_plan(p.planned_id, p.revision, title='Новый', category=p.category, subcategory=p.subcategory)
        self.assertEqual(plans.get_plan(p.planned_id), updated)
        with self.assertRaises(plans.StalePlanError):
            plans.cancel_plan(p.planned_id, p.revision)
        plans.cancel_plan(updated.planned_id, updated.revision)

    def test_create_retry_after_lost_append_response_uses_stable_id(self):
        self.ws.fail_append_after = True
        with self.assertRaises(TimeoutError):
            self.create(planned_id='stable')
        result = self.create(planned_id='stable')
        self.assertEqual(result.planned_id, 'stable')
        self.assertEqual(len(self.ws.rows), 2)

    def test_disabled_guard_does_no_sheet_io(self):
        with patch.object(config, 'PLANNED_EXPENSES_ENABLED', False), patch.object(plans, 'get_spreadsheet') as get:
            for fn, args in ((plans.list_plans, ()), (plans.get_plan, ('x',)), (plans.cancel_plan, ('x','r'))):
                with self.assertRaises(ValueError):
                    fn(*args)
            with self.assertRaises(ValueError), patch.object(plans,'validate_category') as validate:
                plans.update_plan('x','r',title='t',category='c',subcategory='s')
            validate.assert_not_called()
            get.assert_not_called()

    def test_initialize_absent_or_empty_sheet_only_and_preserve_data(self):
        book = Spreadsheet()
        ws = plans.ensure_planned_sheet(book)
        self.assertEqual(ws.rows, [list(plans.HEADERS)])
        plans.ensure_planned_sheet(book)
        self.assertEqual(len(ws.writes), 1)
        ws.rows = [['Неверный заголовок'], ['Данные']]
        with self.assertRaises(ValueError):
            plans.ensure_planned_sheet(book)
        self.assertEqual(ws.rows[1], ['Данные'])

    def test_legacy_schema_upgrade_keeps_rows_and_is_idempotent(self):
        self.ws.rows = [list(plans.LEGACY_HEADERS), ['legacy-id', 'Платёж']]
        plans.ensure_planned_sheet(self.book)
        plans.ensure_planned_sheet(self.book)
        self.assertEqual(self.ws.rows[0], list(plans.HEADERS))
        self.assertEqual(self.ws.rows[1], ['legacy-id', 'Платёж'])
        self.assertEqual(len(self.ws.writes), 1)

    def test_amount_and_date_validation(self):
        for bad in ('NaN','Infinity','0','-1','0,001'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                plans.parse_amount(bad)
        self.assertEqual(plans.parse_amount('1 200,50'), '1200,50')
        with self.assertRaises(ValueError):
            plans.parse_date('21.11.2026', payment=True)
        self.assertEqual(plans.parse_date('сегодня'), '2026-11-20')
        with self.assertRaises(ValueError):
            plans.parse_date('31.02.2026')

    def test_profile_spreadsheets_do_not_share_plan_cache(self):
        first = self.create()
        other = Spreadsheet(Sheet('Будущие_траты', [list(plans.HEADERS)], 33))
        with patch.object(plans, 'get_spreadsheet', return_value=other):
            # Worksheet cache belongs to the selected runtime, reset when adapter changes.
            google_sheets.reset_google_sheets_cache()
            self.assertEqual(plans.list_plans(), [])
            with self.assertRaises(ValueError):
                plans.get_plan(first.planned_id)


if __name__ == '__main__':
    unittest.main()
