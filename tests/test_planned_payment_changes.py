import json
import unittest

import test_planned_expenses as fixtures
from services import planned_expenses as plans
from services.planned_payment_changes import correct_payment


class PaymentCorrectionTests(fixtures.PlannedFixture, unittest.TestCase):
    def test_payer_can_correct_date_and_amount_then_undo_and_pay_again(self):
        plan = self.create()
        paid = plans.pay_plan(plan.planned_id, plan.revision, amount='55', payment_date='2026-11-19',
                              actor='@alice', actor_id=101)
        with self.assertRaises(ValueError):
            correct_payment(paid.planned_id, paid.revision, user_id=202, username='alice', undo=True)
        corrected = correct_payment(paid.planned_id, paid.revision, user_id=101, username='changed',
                                    amount='57,25', payment_date='2026-10-31')
        self.assertEqual(self.expenses.rows[1][:2], ['2026-10-31', '2026-10'])
        self.assertEqual(self.expenses.rows[1][5], '57.25')
        with self.assertRaises(plans.StalePlanError):
            correct_payment(paid.planned_id, paid.revision, user_id=101, username='alice', undo=True)
        reopened = correct_payment(paid.planned_id, corrected.revision, user_id=101, username='alice', undo=True)
        self.assertEqual(reopened.status, 'pending')
        self.assertEqual(self.expenses.rows[1], [''] * 8)
        self.assertEqual([event['action'] for event in json.loads(reopened.payment_history)], ['edit', 'undo'])
        new = plans.pay_plan(reopened.planned_id, reopened.revision, amount='50', payment_date='2026-11-20', actor='@alice')
        self.assertNotEqual(new.expense_id, paid.expense_id)

    def test_late_correction_cannot_overwrite_a_successful_reversal(self):
        plan = self.create()
        paid = plans.pay_plan(plan.planned_id, plan.revision, amount='10', payment_date='2026-11-19',
                              actor='@alice', actor_id=101)
        self.book.deferred_batch = False
        with self.assertRaises(TimeoutError):
            correct_payment(paid.planned_id, paid.revision, user_id=101, username='alice', amount='12')
        late = self.book.deferred_batch
        correct_payment(paid.planned_id, paid.revision, user_id=101, username='alice', undo=True)
        with self.assertRaises(ValueError):
            self.book.apply_batch(late)
        self.assertEqual(plans.get_plan(paid.planned_id).status, 'pending')
        self.assertEqual(self.expenses.rows[1], [''] * 8)
