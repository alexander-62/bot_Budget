from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

original_exists = Path.exists
with patch.object(Path, "exists", lambda path: False if path.name == ".env" else original_exists(path)):
    import config
    from services import expenses, money_sources, startup_validation, google_sheets
from services.bot_profiles import BotProfile, _validate


class ExpenseSheet:
    title = "Expenses"

    def __init__(self):
        self.row = []
        self.deleted = False
        self.range = ""

    def append_row(self, values, **kwargs):
        self.table_range = kwargs["table_range"]
        self.row = [str(value).removeprefix("'") for value in values]
        return {"updates": {"updatedRange": "Expenses!A2:I2"}}

    def col_values(self, column):
        return ["header", self.row[0]]

    def get(self, area):
        return [self.row[:9 if ":I" in area else 8 if ":H" in area else 7]]

    def update(self, *, range_name, values, **kwargs):
        self.range = range_name
        self.row[:len(values[0])] = [str(value).removeprefix("'") for value in values[0]]

    def delete_rows(self, row):
        self.deleted = True


class MoneySourceTests(unittest.TestCase):
    def test_sources_sort_deduplicate_and_ignore_inactive(self):
        rows = [["источник", "активно", "порядок"], ["Карта", "TRUE", "2"], ["Наличные", "да", "1"], [" карта ", "1", "3"], ["Hidden", "false", "0"]]
        self.assertEqual(money_sources.parse_money_sources(rows), ["Наличные", "Карта"])
        with patch.object(money_sources, "TRACK_MONEY_SOURCE", False), patch.object(money_sources, "get_spreadsheet", side_effect=AssertionError("No request when disabled")):
            self.assertEqual(money_sources.get_money_sources(), [])

    def test_profile_flag_defaults_false_and_requires_boolean(self):
        profile = BotProfile("work", "Work", "sheet")
        self.assertFalse(profile.track_money_source)
        with self.assertRaises(ValueError):
            _validate(replace(profile, track_money_source="false"))

    def test_enabled_append_edit_historical_source_and_stale_delete(self):
        sheet = ExpenseSheet()
        with patch.object(expenses, "TRACK_MONEY_SOURCE", True), patch.object(expenses, "get_spreadsheet", return_value=object()), patch.object(expenses, "find_worksheet_case_insensitive", return_value=sheet), patch.object(expenses, "validate_money_source", return_value="Карта") as validate:
            saved = expenses.write_expense("@u", "C", "S", "10,25", money_source="Карта")
            self.assertEqual(sheet.table_range, "A:I")
            self.assertEqual(sheet.row[7], saved.expense_id)
            self.assertEqual(sheet.row[8], "Карта")
            self.assertEqual(saved.money_source, "Карта")
            validate.reset_mock()
            updated = expenses.update_expense(saved, "12,50", "Comment")
            validate.assert_not_called()  # Historical deactivated source remains valid.
            self.assertEqual(updated.money_source, "Карта")
            self.assertEqual(sheet.row[8], "Карта")
            updated = expenses.update_expense(updated, "12,50", "Comment", money_source="Наличные")
            validate.assert_called_once_with("Наличные")
            self.assertEqual(updated.money_source, "Наличные")
            self.assertEqual(sheet.row[8], "Наличные")
            sheet.row[8] = "Someone changed source"
            with self.assertRaises(expenses.StaleExpenseError):
                expenses.delete_expense(updated)
            self.assertFalse(sheet.deleted)

    def test_active_source_is_revalidated_and_disabled_edit_preserves_column_i(self):
        sheet = ExpenseSheet()
        with patch.object(expenses, "TRACK_MONEY_SOURCE", True), patch.object(expenses, "validate_money_source", side_effect=money_sources.MoneySourceError("Inactive")), patch.object(expenses, "get_spreadsheet") as get:
            with self.assertRaises(money_sources.MoneySourceError):
                expenses.write_expense("u", "c", "s", "1", money_source="old")
            get.assert_not_called()
        with patch.object(expenses, "TRACK_MONEY_SOURCE", False), patch.object(expenses, "get_spreadsheet", return_value=object()), patch.object(expenses, "find_worksheet_case_insensitive", return_value=sheet), patch.object(expenses, "validate_money_source", side_effect=AssertionError("Disabled")):
            saved = expenses.write_expense("u", "c", "s", "1")
            self.assertEqual(sheet.table_range, "A:H")
            sheet.row.append("Historical source")
            expenses.update_expense(saved, "2")
            self.assertEqual(sheet.row[8], "Historical source")
            self.assertEqual(len(expenses.get_recent_expenses()[0]), 6)
            self.assertEqual(expenses.get_recent_expenses(include_source=True)[0][6], "Historical source")
            sheet.row = sheet.row[:8]
            self.assertEqual(expenses.get_recent_expenses(include_source=True)[0][6], "")

    def test_disabled_feature_keeps_source_identity_guard_for_existing_saved_record(self):
        sheet = ExpenseSheet()
        with patch.object(expenses, "TRACK_MONEY_SOURCE", True), patch.object(expenses, "get_spreadsheet", return_value=object()), patch.object(expenses, "find_worksheet_case_insensitive", return_value=sheet), patch.object(expenses, "validate_money_source"):
            saved = expenses.write_expense("u", "c", "s", "1", money_source="Карта")
        with patch.object(expenses, "TRACK_MONEY_SOURCE", False), patch.object(expenses, "_get_expenses_worksheet", return_value=sheet):
            expenses.update_expense(saved, "2")
            self.assertEqual(sheet.row[8], "Карта")
            sheet.row[8] = "Changed"
            with self.assertRaises(expenses.StaleExpenseError):
                expenses.delete_expense(replace(saved, amount="2"))

    def test_enabled_connection_requires_source_column_sheet_and_active_values(self):
        profile = BotProfile("work", "Work", "sheet", track_money_source=True)
        rules = startup_validation.get_worksheet_rules(profile)
        worksheets = []
        for rule in rules:
            header = list(rule.required_headers)
            if rule.name == startup_validation.EXPENSES_SHEET_NAME:
                header += ["комментарий", "expense_id", "источник"]
            worksheet = Mock(title=rule.name)
            worksheet.row_values.return_value = header
            worksheet.get_all_values.return_value = [header]
            worksheets.append(worksheet)
        spreadsheet = Mock()
        spreadsheet.worksheets.return_value = worksheets
        with patch.object(google_sheets, "open_profile_spreadsheet", return_value=spreadsheet):
            with self.assertRaisesRegex(ValueError, "активный"):
                google_sheets.validate_profile_connection(profile, Path("fake-key"))
            worksheets[-1].get_all_values.return_value += [["Карта", "true", "1"]]
            self.assertTrue(google_sheets.validate_profile_connection(profile, Path("fake-key")))
            expense_sheet = worksheets[3]
            expense_sheet.row_values.return_value = expense_sheet.row_values.return_value[:8]
            with self.assertRaises(ValueError):
                google_sheets.validate_profile_connection(profile, Path("fake-key"))


if __name__ == "__main__":
    unittest.main()
