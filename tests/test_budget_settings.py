"""Budget preferences migrate once and remain Sheet-owned across processes."""
import copy
from contextlib import ExitStack
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

import config
from services import budget_settings as settings, budget, google_sheets
from services.money import currency_symbol


class Sheet:
    def __init__(self, title, rows=None):
        self.title, self.rows = title, rows or []
        self.writes = []

    def get_all_values(self):
        return copy.deepcopy(self.rows)

    def row_values(self, number):
        return list(self.rows[number-1])

    def update(self, range_name, values, **kwargs):
        self.writes.append((range_name, values, kwargs))
        column = ord(range_name[0]) - ord('A')
        row = int(''.join(c for c in range_name.split(':')[0] if c.isdigit())) - 1
        while len(self.rows) <= row:
            self.rows.append([])
        for offset, cells in enumerate(values):
            while len(self.rows[row+offset]) < column + len(cells):
                self.rows[row+offset].append('')
            self.rows[row+offset][column:column+len(cells)] = cells

    def append_rows(self, values, **kwargs):
        self.writes.append(('append', values, kwargs))
        self.rows.extend(copy.deepcopy(values))

    def append_row(self, values, **kwargs):
        self.append_rows([values], **kwargs)


class Spreadsheet:
    def __init__(self, *sheets):
        self.sheets = list(sheets)

    def worksheets(self):
        return list(self.sheets)

    def add_worksheet(self, title, **kwargs):
        sheet = Sheet(title)
        self.sheets.append(sheet)
        return sheet


def configured(currency='EUR', enabled='TRUE'):
    return Spreadsheet(Sheet('Настройки', [settings.HEADER, ['currency', currency], ['monthly_limits_enabled', enabled]]))


class BudgetSettingsTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(settings, '_runtime', None))
        self.stack.enter_context(patch.object(settings, '_loaded_at', 0))
        google_sheets.reset_google_sheets_cache()
        budget.clear_budget_snapshot_cache()
        self.addCleanup(google_sheets.reset_google_sheets_cache)
        self.addCleanup(budget.clear_budget_snapshot_cache)

    def test_migration_uses_local_currency_only_for_missing_keys(self):
        sheet = Spreadsheet()
        self.assertEqual(settings.ensure_settings(sheet, 'RUB'), settings.BudgetSettings('RUB', True))
        before = copy.deepcopy(sheet.sheets[0].rows)
        writes = len(sheet.sheets[0].writes)
        self.assertEqual(settings.ensure_settings(sheet, 'EUR').currency, 'RUB')
        self.assertEqual(sheet.sheets[0].rows, before)
        self.assertEqual(len(sheet.sheets[0].writes), writes)

    def test_real_empty_sheet_shapes_initialize_headers_and_defaults(self):
        for rows in ([[]], [["", ""]], [["  ", ""]]):
            with self.subTest(rows=rows):
                spreadsheet = Spreadsheet(Sheet('Настройки', copy.deepcopy(rows)))
                self.assertEqual(settings.ensure_settings(spreadsheet, 'RUB'), settings.BudgetSettings('RUB', True))
                self.assertEqual(spreadsheet.sheets[0].rows[0], settings.HEADER)
                self.assertEqual(len(spreadsheet.sheets[0].rows), 3)
                writes = len(spreadsheet.sheets[0].writes)
                settings.ensure_settings(spreadsheet, 'EUR')
                self.assertEqual(len(spreadsheet.sheets[0].writes), writes)

    def test_partial_migration_preserves_false_and_unknown_settings(self):
        sheet = Spreadsheet(Sheet('Настройки', [settings.HEADER, ['monthly_limits_enabled', 'FALSE'], ['custom', 'keep']]))
        self.assertEqual(settings.ensure_settings(sheet, 'RUB'), settings.BudgetSettings('RUB', False))
        self.assertIn(['custom', 'keep'], sheet.sheets[0].rows)

    def test_invalid_existing_or_duplicate_values_are_not_overwritten(self):
        for rows in ([settings.HEADER, ['currency', 'USD']],
                     [settings.HEADER, ['currency', 'EUR'], ['currency', 'RUB']],
                     [['wrong', 'header']],
                     [settings.HEADER, ['monthly_limits_enabled', 'maybe']]):
            sheet = Spreadsheet(Sheet('Настройки', copy.deepcopy(rows)))
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                settings.ensure_settings(sheet, 'EUR')
            self.assertEqual(sheet.sheets[0].rows, rows)
            self.assertFalse(sheet.sheets[0].writes)

    def test_updates_only_selected_key_and_checks_expected_currency(self):
        sheet = configured()
        settings.update_setting(sheet, 'currency', 'RUB', expected='EUR')
        self.assertTrue(settings.read_settings(sheet).monthly_limits_enabled)
        with self.assertRaises(ValueError):
            settings.update_setting(sheet, 'currency', 'EUR', expected='EUR')
        settings.update_setting(sheet, 'monthly_limits_enabled', 'FALSE')
        self.assertEqual(settings.read_settings(sheet), settings.BudgetSettings('RUB', False))
        self.assertEqual([x[0] for x in sheet.sheets[0].writes], ['B2', 'B3'])

    def test_runtime_refreshes_and_formats_without_network_on_event_loop(self):
        sheet = configured('RUB')
        with patch.object(settings, 'get_spreadsheet', return_value=sheet) as get:
            settings.initialize_runtime_settings()
            self.assertEqual(currency_symbol(), '₽')
            calls = get.call_count
            settings.refresh_runtime_settings()
            currency_symbol()
            self.assertEqual(get.call_count, calls)
            sheet.sheets[0].rows[1][1] = 'EUR'
            settings.refresh_runtime_settings(force=True)
            self.assertEqual(currency_symbol(), '€')

    def test_explicit_profile_reads_do_not_pollute_runtime_settings(self):
        with patch.object(settings, 'get_spreadsheet', return_value=configured('EUR')):
            settings.initialize_runtime_settings()
        other = configured('RUB')
        settings.update_setting(other, 'monthly_limits_enabled', 'FALSE')
        self.assertEqual(currency_symbol(), '€')
        self.assertTrue(settings.cached_settings().monthly_limits_enabled)

    def test_failed_refresh_does_not_publish_defaults(self):
        with patch.object(settings, 'get_spreadsheet', return_value=configured('RUB')):
            settings.initialize_runtime_settings()
        with patch.object(settings, 'get_spreadsheet', side_effect=OSError('offline')), self.assertRaises(OSError):
            settings.refresh_runtime_settings(force=True)
        self.assertEqual(settings.cached_settings().currency, 'RUB')

    def test_connection_validation_is_read_only_and_disabled_limits_optional(self):
        sheet = configured(enabled='FALSE')
        from services.startup_validation import get_worksheet_rules
        profile = SimpleNamespace(currency='EUR', legacy=True, track_money_source=False)
        for rule in get_worksheet_rules(profile, limits_enabled=False):
            sheet.sheets.append(Sheet(rule.name, [list(rule.required_headers)]))
        with patch.object(google_sheets, 'open_profile_spreadsheet', return_value=sheet):
            self.assertTrue(google_sheets.validate_profile_connection(profile, 'unused'))
        self.assertFalse(any(s.writes for s in sheet.sheets))

    def test_desktop_currency_uses_captured_profile_and_expected_sheet_value(self):
        import desktop_app as desktop
        profile = replace(config.PROFILE, id='work', spreadsheet_id='sheet-work', legacy=False, currency='EUR')
        context = {'profile':profile, 'settings':settings.BudgetSettings('RUB')}
        sheet = configured('RUB')
        with patch.object(google_sheets, 'open_profile_spreadsheet', return_value=sheet) as opening:
            result = desktop.profile_currency_operation(context, 'EUR')
        self.assertIs(result[0], context)
        self.assertEqual(result[1].currency, 'EUR')
        self.assertEqual(opening.call_args.args[0].id, 'work')
        self.assertIsNone(settings._runtime)


class OptionalLimitsTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(settings, '_runtime', settings.BudgetSettings('RUB', False)))
        self.sheet = Spreadsheet(
            Sheet('Категории', [['Категория','Подкатегория','Активно','Порядок'], ['Еда','Кафе','TRUE','1'], ['Архив','Старое','FALSE','2']]),
            Sheet('Траты_по_месяцам', [['Дата','Месяц','Пользователь','Категория','Подкатегория','Сумма'],
                                      ['2026-10-01','2026-10','u','Еда','Кафе','10'],
                                      ['2026-10-01','2026-10','u','Архив','Старое','20']]))
        self.stack.enter_context(patch.object(budget, 'get_spreadsheet', return_value=self.sheet))
        self.stack.enter_context(patch.object(budget, 'get_current_month_key', return_value='2026-10'))
        google_sheets.reset_google_sheets_cache()
        budget.clear_budget_snapshot_cache()
        self.addCleanup(google_sheets.reset_google_sheets_cache)
        self.addCleanup(budget.clear_budget_snapshot_cache)

    def test_disabled_mode_needs_no_limit_sheet_and_keeps_archived_spending(self):
        self.assertEqual(budget.get_month_totals(), ('—','30,00','—'))
        self.assertEqual(budget.get_report_categories(), ['Еда','Архив'])
        self.assertEqual(budget.get_budget_limits()[1], ['Еда'])
        self.assertEqual(budget.get_subcategories_for_category('Архив'), [])
        self.assertEqual(budget.get_category_details('Архив')[2], '20,00')
        from services.budget_views import format_category_card
        text = format_category_card(budget.get_category_details('Еда'))
        self.assertIn('10 ₽', text)
        self.assertNotIn('Лимит', text)
        self.assertNotIn('Осталось', text)
        self.assertNotIn('⚠', text)

    def test_zero_limit_differs_from_blank_or_missing_limit(self):
        settings._runtime = settings.BudgetSettings('RUB', True)
        self.sheet.sheets.append(Sheet('Лимиты_по_месяцам', [['Категория','Подкатегория','2026-10'], ['Еда','Кафе','0'], ['Архив','Старое','']]))
        self.assertEqual(budget.get_category_details('Еда')[1:4], ('0,00','10,00','-10,00'))
        self.assertEqual(budget.get_category_details('Архив')[1:4], ('—','20,00','—'))
        self.assertEqual(budget.get_month_totals(), ('—','30,00','—'))

    def test_turning_mode_off_and_on_preserves_limits(self):
        self.sheet.sheets.append(Sheet('Лимиты_по_месяцам', [['Категория','Подкатегория','2026-10'], ['Еда','Кафе','100'], ['Архив','Старое','50']]))
        self.assertEqual(budget.get_month_totals(), ('—','30,00','—'))
        settings._publish(settings.BudgetSettings('RUB', True))
        self.assertEqual(budget.get_month_totals(), ('150,00','30,00','120,00'))
        self.assertFalse(self.sheet.sheets[-1].writes)


if __name__ == '__main__':
    unittest.main()
