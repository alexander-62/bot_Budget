from datetime import date
import unittest
from unittest.mock import patch

import test_planned_expenses as fixtures
from services import planned_expenses as plans, planned_recurrence as repeat


class RecurrenceTests(fixtures.PlannedFixture, unittest.TestCase):
    def test_monthly_uses_original_day_after_short_month_and_keeps_overdue(self):
        plan = self.create(due_date='2026-01-31')
        repeat.set_recurrence(plan.planned_id, plan.revision, 'monthly')
        repeat.advance_due_series(date(2026, 1, 31))
        repeat.advance_due_series(date(2026, 1, 31))
        repeat.advance_due_series(date(2026, 2, 28))
        records = plans.list_plans()
        self.assertEqual({p.due_date for p in records}, {'2026-01-31', '2026-02-28', '2026-03-31'})
        self.assertEqual([p.due_date for p in records if p.repeat_rule], ['2026-03-31'])

    def test_retry_after_ambiguous_response_creates_one_occurrence(self):
        plan = self.create(due_date='2026-11-20')
        repeat.set_recurrence(plan.planned_id, plan.revision, 'weekly')
        self.book.deferred_batch = False
        with self.assertLogs(level='ERROR'):
            repeat.advance_due_series(date(2026, 11, 20))
        first = self.book.deferred_batch
        repeat.advance_due_series(date(2026, 11, 20))
        with self.assertRaises(ValueError):
            self.book.apply_batch(first)
        self.assertEqual(len(plans.list_plans()), 2)

    def test_cancelling_active_occurrence_stops_series(self):
        plan = self.create(due_date='2026-11-20')
        plan = repeat.set_recurrence(plan.planned_id, plan.revision, 'weekly')
        plans.cancel_plan(plan.planned_id, plan.revision)
        repeat.advance_due_series(date(2026, 11, 20))
        self.assertEqual(plans.list_plans(), [])
