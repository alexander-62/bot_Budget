from datetime import date
import unittest
from unittest.mock import patch

import test_planned_expenses as fixtures
from services import planned_forecast


class ForecastTests(fixtures.PlannedFixture, unittest.TestCase):
    def test_overlapping_windows_at_month_end_and_missing_amounts(self):
        for due, amount in [('2026-01-30', '10'), ('2026-02-01', '20'),
                            ('2026-01-29', '30'), ('2026-01-31', ''), ('', '40'),
                            ('2026-02-05', '5'), ('2026-02-06', '100')]:
            self.create(due_date=due, amount=amount)
        with patch.object(planned_forecast, 'format_money_exact', side_effect=lambda amount: f'{amount:.2f}'):
            message = planned_forecast.forecast_message(date(2026, 1, 30))
        self.assertIn('7 дней (до 05.02): 35.00, без суммы — 1', message)
        self.assertIn('конца месяца (до 31.01): 10.00, без суммы — 1', message)
        self.assertIn('Просроченные: 30.00', message)
        self.assertIn('Без даты: 40.00', message)
        self.assertNotIn('100.00', message)
