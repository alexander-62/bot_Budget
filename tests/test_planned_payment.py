from concurrent.futures import ThreadPoolExecutor
from datetime import date
from unittest.mock import patch, Mock
import unittest

import test_planned_expenses as fixtures
from services import planned_expenses as plans, expenses


class PlannedPaymentTests(fixtures.PlannedFixture, unittest.TestCase):
    @property
    def payment_batches(self):
        return [batch for batch in self.book.batches
                if any(request.get('appendCells', {}).get('sheetId') == self.expenses.id
                       for request in batch['requests'])]

    def pay(self, p, **kwargs):
        args = dict(amount='125,75', payment_date='2026-10-31', actor='@bob')
        args.update(kwargs)
        return plans.pay_plan(p.planned_id, p.revision, **args)

    def test_payment_atomically_closes_plan_and_records_actual_date_actor_and_amount(self):
        p = self.create(amount='120')
        result = self.pay(p)
        self.assertEqual(result.status, 'paid')
        self.assertEqual(result.creator, '@alice')
        self.assertEqual(result.paid_by, '@bob')
        self.assertEqual(self.expenses.rows[1][:6], ['2026-10-31','2026-10','@bob','Авто','Страхование','125.75'])
        self.assertEqual(self.expenses.rows[1][7], result.expense_id)
        self.assertEqual(plans.get_plan(p.planned_id).status, 'paid')
        self.assertEqual(len(self.payment_batches), 1)
        self.assertEqual(len(self.payment_batches[0]['requests']), 5)
        self.assertEqual(plans.list_plans(), [])

    def test_double_click_and_two_users_do_not_duplicate(self):
        p = self.create()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda actor: self.pay(p, actor=actor), ['@bob','@carol']))
        self.assertEqual(results[0].expense_id, results[1].expense_id)
        self.assertEqual(len(self.expenses.rows), 2)

    def test_lost_batch_response_recovers_from_sheet_after_restart(self):
        p = self.create()
        self.book.batch_error_after = True
        with self.assertRaises(TimeoutError):
            self.pay(p)
        # All recovery state is in Sheets; a fresh invocation has no in-memory token dependency.
        self.assertEqual(self.pay(p).status, 'paid')
        self.assertEqual(len(self.expenses.rows), 2)
        self.assertEqual(len(self.payment_batches), 1)

    def test_still_in_flight_transaction_cannot_be_dispatched_twice(self):
        p = self.create()
        self.book.deferred_batch = False
        with self.assertRaises(TimeoutError):
            self.pay(p)
        self.assertEqual(plans.get_plan(p.planned_id).status, 'processing')
        with self.assertRaises(ValueError):
            self.pay(p)
        self.assertEqual(len(self.payment_batches), 1)
        # First HTTP request eventually commits; checking again reads paid.
        self.book.apply_batch(self.book.deferred_batch)
        self.assertEqual(self.pay(p).status, 'paid')
        self.assertEqual(len(self.expenses.rows), 2)

    def test_stale_or_cancelled_plan_and_invalid_payment_are_rejected_before_writes(self):
        p = self.create()
        with self.assertRaises(ValueError):
            self.pay(p, payment_date='2027-01-01')
        self.assertEqual(plans.get_plan(p.planned_id).status, 'pending')
        plans.cancel_plan(p.planned_id, p.revision)
        with self.assertRaises(ValueError):
            self.pay(p)
        self.assertEqual(len(self.expenses.rows), 1)

    def test_definite_rejection_keeps_expense_absent_and_allows_fresh_confirmation(self):
        from gspread.exceptions import APIError
        response=Mock()
        response.json.return_value={'error':{'code':400,'message':'Invalid request','status':'INVALID_ARGUMENT'}}
        p=self.create()
        self.book.batch_error_before=APIError(response)
        with self.assertRaises(APIError):
            self.pay(p)
        latest=plans.get_plan(p.planned_id)
        self.assertEqual(latest.status,'pending')
        self.assertNotEqual(latest.revision,p.revision)
        self.assertEqual(len(self.expenses.rows),1)
        self.book.batch_error_before=None
        self.pay(latest)
        self.assertEqual(len(self.expenses.rows),2)

    def test_payment_records_source_when_tracking_is_enabled(self):
        p=self.create()
        with patch('config.TRACK_MONEY_SOURCE',True),patch.object(expenses,'TRACK_MONEY_SOURCE',True), \
             patch('services.money_sources.validate_money_source') as validate, patch.object(expenses,'validate_money_source'):
            self.pay(p,money_source='=Карта')
            self.assertTrue(validate.called)
            self.assertEqual(self.expenses.rows[1][8],'=Карта')


    def test_formula_like_text_is_explicit_string_value_in_atomic_write(self):
        p = self.create(title='=FORMULA()', comment='+comment')
        self.pay(p)
        cells = self.payment_batches[0]['requests'][1]['appendCells']['rows'][0]['values']
        self.assertEqual(cells[6]['userEnteredValue'], {'stringValue': '=FORMULA() — +comment'})
        self.assertIn('numberValue', cells[5]['userEnteredValue'])

    def test_actual_expense_writer_accepts_explicit_date_and_keeps_default_compatibility(self):
        with patch.object(expenses, 'get_current_month_key', side_effect=lambda d: d.strftime('%Y-%m')):
            saved = expenses.write_expense('@bob','Авто','Страхование','12,50',expense_date=date(2020,1,31))
        self.assertEqual(saved.date, '2020-01-31')
        self.assertEqual(saved.month_key, '2020-01')


if __name__ == '__main__':
    unittest.main()
