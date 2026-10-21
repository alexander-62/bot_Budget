"""Verify the real profile form passes a boolean setting to its save worker."""
from pathlib import Path
import tkinter
import unittest
from unittest.mock import Mock, patch

original_exists = Path.exists
with patch.object(Path, "exists", lambda path: False if path.name == ".env" else original_exists(path)):
    import desktop_app
from services.bot_profiles import BotProfile


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class MoneySourceDesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            root = tkinter.Tk()
            root.destroy()
        except tkinter.TclError as error:
            raise unittest.SkipTest(str(error))

    def setUp(self):
        self.personal = BotProfile("personal", "Personal", "", legacy=True)
        self.patchers = [
            patch.object(desktop_app, "list_profiles", return_value=[self.personal]),
            patch.object(desktop_app, "WindowsAutostart", return_value=Mock(supported=False)),
            patch.object(desktop_app.BudgetPanel, "_submit"),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.panel = desktop_app.BudgetPanel()

    def tearDown(self):
        if self.panel._editor is not None and self.panel._editor.winfo_exists():
            self.panel._editor.destroy()
        for callback in self.panel.tk.call("after", "info"):
            self.panel.after_cancel(callback)
        self.panel._quit()

    def submit(self):
        button = next(widget for widget in descendants(self.panel._editor)
                      if isinstance(widget, desktop_app.ctk.CTkButton)
                      and widget.cget("text") == "Проверить и сохранить")
        self.panel._submit.reset_mock()
        button.invoke()
        self.panel._submit.assert_called_once()
        args = self.panel._submit.call_args.args
        self.assertEqual(args[0], "profile-save")
        self.assertIs(args[1], desktop_app.save_validated_profile)
        return args[2]

    def test_new_form_defaults_off_and_can_submit_enabled_profile(self):
        self.panel._show_profile_editor(None)
        self.assertFalse(self.panel._editor_source_tracking.get())
        entries = [widget for widget in descendants(self.panel._editor)
                   if isinstance(widget, desktop_app.ctk.CTkEntry)]
        # Entry order is name, id, sheet, timezone, credentials, token.
        for widget, value in zip(entries, ["Business", "business", "business-sheet", "Europe/Moscow", "", "123:fake"]):
            widget.delete(0, "end")
            widget.insert(0, value)
        self.panel._editor_source_tracking.set(True)
        candidate = self.submit()
        self.assertEqual(candidate.id, "business")
        self.assertIs(candidate.track_money_source, True)

    def test_edit_reflects_enabled_setting_and_preserves_other_profile_fields(self):
        profile = BotProfile("business", "Business", "sheet", "RUB", track_money_source=True)
        self.panel._show_profile_editor(profile)
        self.assertTrue(self.panel._editor_source_tracking.get())
        self.panel._editor_source_tracking.set(False)
        candidate = self.submit()
        self.assertIs(candidate.track_money_source, False)
        self.assertEqual(candidate.id, profile.id)
        self.assertEqual(candidate.currency, "RUB")
        self.assertEqual(candidate.spreadsheet_id, profile.spreadsheet_id)


if __name__ == "__main__":
    unittest.main()
