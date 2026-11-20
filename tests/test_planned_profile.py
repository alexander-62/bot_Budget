from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tkinter
import unittest
from unittest.mock import Mock, patch

from services.bot_profiles import BotProfile, list_profiles, _validate
from services.startup_validation import get_worksheet_rules, validate_worksheet_header
from constants import PLANNED_EXPENSES_SHEET_NAME, EXPENSES_SHEET_NAME


class PlannedProfileTests(unittest.TestCase):
    def test_old_registry_defaults_off_and_rejects_non_boolean_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'profiles.json'
            values=asdict(BotProfile('personal','Personal','',legacy=True))
            del values['planned_expenses_enabled']
            path.write_text(json.dumps({'profiles':[values]}),encoding='utf-8')
            self.assertIs(list_profiles(Path(directory))[0].planned_expenses_enabled,False)
        with self.assertRaises(ValueError):
            _validate(BotProfile('personal','Personal','',legacy=True,planned_expenses_enabled='true'))

    def test_disabled_profile_does_not_require_optional_sheet(self):
        profile=BotProfile('business','Business','sheet')
        self.assertNotIn(PLANNED_EXPENSES_SHEET_NAME,[r.name for r in get_worksheet_rules(profile)])
        enabled=replace(profile,planned_expenses_enabled=True)
        self.assertIn(PLANNED_EXPENSES_SHEET_NAME,[r.name for r in get_worksheet_rules(enabled)])
        rule=next(r for r in get_worksheet_rules(enabled) if r.name==EXPENSES_SHEET_NAME)
        header=['Дата','Месяц','Пользователь','Категория','Подкатегория','Сумма']
        with self.assertRaises(ValueError):
            validate_worksheet_header(rule,header,legacy=True,planned_expenses_enabled=True)
        validate_worksheet_header(rule,header+['Комментарий','expense_id'],legacy=True,planned_expenses_enabled=True)

    def test_connection_is_read_only_and_startup_initializes_only_enabled_feature(self):
        from services import google_sheets, startup_validation
        from services.budget_settings import BudgetSettings
        from services.planned_expenses import HEADERS
        from planned_fakes import Sheet, Spreadsheet
        profile=BotProfile('business','Business','sheet',planned_expenses_enabled=True)
        for existing_empty in (False,True):
            with self.subTest(existing_empty=existing_empty):
                google_sheets.reset_google_sheets_cache()
                sheets=[]
                for index,rule in enumerate(get_worksheet_rules(profile),1):
                    if rule.name==PLANNED_EXPENSES_SHEET_NAME:
                        if existing_empty:sheets.append(Sheet(rule.name,[[]],index))
                        continue
                    header=list(rule.required_headers)
                    if rule.name==EXPENSES_SHEET_NAME:header+=['Комментарий','expense_id']
                    sheets.append(Sheet(rule.name,[header],index))
                book=Spreadsheet(*sheets)
                with patch.object(google_sheets,'open_profile_spreadsheet',return_value=book):
                    self.assertTrue(google_sheets.validate_profile_connection(profile,'unused'))
                self.assertTrue(all(not ws.writes for ws in sheets))
                with patch.object(startup_validation,'PROFILE',profile), \
                     patch.object(startup_validation,'get_spreadsheet',return_value=book), \
                     patch('services.budget_settings.initialize_runtime_settings',return_value=BudgetSettings()):
                    startup_validation._validate_google_sheets_schema()
                self.assertEqual(next(ws for ws in book.worksheets() if ws.title==PLANNED_EXPENSES_SHEET_NAME).row_values(1),list(HEADERS))
        google_sheets.reset_google_sheets_cache()


    def test_main_menu_obeys_runtime_flag(self):
        from keyboards import main
        for flag in (False,True):
            with patch.object(main,'PLANNED_EXPENSES_ENABLED',flag):
                labels=[b.text for row in main.build_main_menu().keyboard for b in row]
                self.assertEqual('📅 Будущие траты' in labels,flag)


class PlannedDesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            root=tkinter.Tk();root.destroy()
        except tkinter.TclError as error:
            raise unittest.SkipTest(str(error))

    def test_editor_saves_boolean_and_requests_restart_only_when_flag_changed(self):
        import desktop_app
        profile=BotProfile('business','Business','sheet',track_money_source=True)
        with patch.object(desktop_app,'list_profiles',return_value=[profile]), \
             patch.object(desktop_app,'WindowsAutostart',return_value=Mock(supported=False)), \
             patch.object(desktop_app.BudgetPanel,'_submit'):
            panel=desktop_app.BudgetPanel()
            try:
                panel._show_profile_editor(profile)
                self.assertFalse(panel._editor_planned_expenses.get())
                panel._editor_planned_expenses.set(True)
                def descendants(widget):
                    for child in widget.winfo_children():
                        yield child
                        yield from descendants(child)
                button=next(w for w in descendants(panel._editor) if isinstance(w,desktop_app.ctk.CTkButton)
                            and w.cget('text')=='Проверить и сохранить')
                panel._submit.reset_mock();button.invoke()
                candidate=panel._submit.call_args.args[2]
                self.assertIs(candidate.planned_expenses_enabled,True)
                self.assertTrue(candidate.track_money_source)
                self.assertTrue(desktop_app.runtime_settings_changed(candidate,profile,''))
                self.assertFalse(desktop_app.runtime_settings_changed(profile,profile,''))
            finally:
                if panel._editor:panel._editor.destroy()
                for callback in panel.tk.call('after','info'):panel.after_cancel(callback)
                panel._quit()


if __name__=='__main__':unittest.main()
