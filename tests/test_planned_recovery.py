from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_planned_expenses as fixtures
from services import planned_expenses as plans
from services import planned_recovery as recovery


class RecoveryTests(fixtures.PlannedFixture, unittest.TestCase):
    def _unconfirmed_payment(self):
        plan = self.create()
        self.book.deferred_batch = False
        with self.assertRaises(TimeoutError):
            plans.pay_plan(plan.planned_id, plan.revision, amount='20', payment_date='2026-11-20',
                           actor='@alice', actor_id=101)
        return plan

    def test_recover_then_late_original_cannot_duplicate_or_change_status(self):
        plan = self._unconfirmed_payment()
        original = self.book.deferred_batch
        item, = recovery.inspect_recovery(self.book)
        self.assertEqual(item.state, 'retry')
        paid = recovery.recover_payment(self.book, item)
        with self.assertRaises(ValueError):
            self.book.apply_batch(original)
        self.assertEqual(plans.get_plan(plan.planned_id), paid)
        self.assertEqual(len(self.expenses.rows), 2)
        self.assertEqual(recovery.recover_payment(self.book, item), paid)

    def test_legacy_with_matching_row_can_close_but_absent_row_cannot_retry(self):
        plan = self.create()
        processing = replace(plan, status='processing', expense_id='legacy-payment',
                             actual_amount='20,00', actual_date='2026-11-20', paid_by='@alice')
        self.ws.rows[0] = list(plans.LEGACY_HEADERS)
        self.ws.rows[1] = processing.values()[:len(plans.LEGACY_HEADERS)]
        item, = recovery.inspect_recovery(self.book)
        self.assertEqual(item.state, 'legacy')
        with self.assertRaises(ValueError):
            recovery.recover_payment(self.book, item)
        self.expenses.rows.append(['2026-11-20','2026-11','@alice','Авто','Страхование','20','','legacy-payment'])
        self.assertEqual(recovery.inspect_recovery(self.book)[0].state, 'found')
        self.assertEqual(recovery.recover_payment(self.book, item).status, 'paid')
        self.assertEqual(len(self.expenses.rows), 2)

    def test_existing_mismatched_amount_reports_conflict(self):
        plan = self._unconfirmed_payment()
        pending = plans.get_plan(plan.planned_id)
        self.expenses.rows.append(['2026-11-20','2026-11','@alice','Авто','Страхование','21','',pending.expense_id])
        item, = recovery.inspect_recovery(self.book)
        self.assertEqual(item.state, 'conflict')
        with self.assertRaises(ValueError):
            recovery.recover_payment(self.book, item)
        self.assertEqual(plans.get_plan(plan.planned_id).status, 'processing')

    def test_panel_blocks_write_while_selected_bot_owns_its_lock(self):
        import desktop_app
        from services.bot_profiles import BotProfile
        from services.process_control import ProcessLock
        plan = self._unconfirmed_payment()
        item, = recovery.inspect_recovery(self.book)
        profile = BotProfile('team', 'Team', 'test', planned_expenses_enabled=True)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            runtime = profile.runtime_dir(base)
            runtime.mkdir(parents=True)
            with patch.object(desktop_app, 'BASE_DIR', base), patch.object(desktop_app, 'list_profiles', return_value=[profile]), \
                 patch('services.google_sheets.open_profile_spreadsheet', return_value=self.book) as open_book:
                with ProcessLock(runtime / '.bot.lock'):
                    _, records, message = desktop_app.profile_payment_recovery({'profile': profile}, item)
                self.assertIsNone(records)
                self.assertIn('Остановите', message)
                open_book.assert_not_called()
                _, records, _ = desktop_app.profile_payment_recovery({'profile': profile}, item)
                self.assertEqual(records, [])
                self.assertEqual(plans.get_plan(plan.planned_id).status, 'paid')
