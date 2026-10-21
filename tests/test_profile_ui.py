from dataclasses import replace
from queue import Queue
from types import SimpleNamespace
import unittest
import tkinter
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import Mock, patch

import desktop_app
from services.bot_profiles import BotProfile


class ProfileUITests(unittest.TestCase):
    def test_cancel_during_validation_prevents_persistence(self):
        cancelled = Event()
        profile = BotProfile("third", "Third", "sheet3")
        def validate(*args, **kwargs):
            cancelled.set()
            return desktop_app.ValidationResult(True, "ok")
        with patch.object(desktop_app, "list_profiles", return_value=[]), \
             patch.object(desktop_app, "validate_profile", side_effect=validate), \
             patch.object(desktop_app, "save_profile") as save:
            result, saved = desktop_app.save_validated_profile(profile, None, "123:secret", cancelled)
        self.assertIsNone(saved)
        save.assert_not_called()

    def test_worker_started_during_validation_blocks_save(self):
        profile = BotProfile("third", "Third", "sheet3")
        with TemporaryDirectory() as directory, \
             patch.object(desktop_app, "BASE_DIR", Path(directory)), \
             patch.object(desktop_app, "list_profiles", return_value=[]), \
             patch.object(desktop_app, "validate_profile", return_value=desktop_app.ValidationResult(True, "ok")), \
             patch.object(desktop_app, "read_int", return_value=123), \
             patch.object(desktop_app, "is_process_running", return_value=True), \
             patch.object(desktop_app, "save_profile") as save:
            result, saved = desktop_app.save_validated_profile(profile, None, "123:secret", Event())
        self.assertFalse(result.ok)
        self.assertIsNone(saved)
        save.assert_not_called()

    def test_save_completion_keeps_new_selection_and_refreshes_same_selection(self):
        profile = BotProfile("third", "Third updated", "sheet3")
        other = BotProfile("family", "Family", "sheet2")
        for switched in (True, False):
            panel = SimpleNamespace(_save_context=(Mock(), Mock(), Mock(), profile, 1),
                                    _generation=2 if switched else 1,
                                    selected_profile=other if switched else profile,
                                    profile_menu=Mock(), feedback=Mock(), refresh=Mock(),
                                    _profile_labels=Mock(return_value=[]), _profile_label=lambda p: p.name,
                                    _select_profile=Mock())
            with patch.object(desktop_app, "list_profiles", return_value=[other, profile]):
                desktop_app.BudgetPanel._finish_profile_save(panel, (desktop_app.ValidationResult(True, "ok"), profile), None)
            panel._select_profile.assert_not_called()
            self.assertEqual(panel.selected_profile.id, "family" if switched else "third")
            self.assertEqual(panel.refresh.call_count, 0 if switched else 1)
            panel.profile_menu.set.assert_called_once_with(panel.selected_profile.name)

    def test_third_profile_is_selectable_without_special_case(self):
        try:
            probe = tkinter.Tk()
            probe.destroy()
        except tkinter.TclError as error:
            self.skipTest(str(error))
        profiles = [BotProfile("personal", "Personal", "", legacy=True),
                    BotProfile("family", "Family", "sheet2"),
                    BotProfile("third", "Third", "sheet3")]
        with patch.object(desktop_app, "list_profiles", return_value=profiles), \
             patch.object(desktop_app.BudgetPanel, "_submit") as submit, \
             patch.object(desktop_app, "WindowsAutostart", return_value=Mock(supported=False)):
            panel = desktop_app.BudgetPanel()
            try:
                panel._select_profile(panel._profile_label(profiles[2]))
                self.assertEqual(panel.selected_profile.id, "third")
                self.assertIsNone(panel._last_status)
                self.assertEqual(panel.action_buttons["start"].cget("state"), "disabled")
                self.assertEqual(submit.call_args.args[0], ("status", 1))
            finally:
                for callback in panel.tk.call("after", "info"):
                    panel.after_cancel(callback)
                panel._quit()

    def test_actions_and_log_target_selected_profile(self):
        panel = SimpleNamespace(_busy=False, _closed=False, _generation=9,
                                selected_profile=BotProfile("third", "Third", "sheet3"),
                                _update_buttons=Mock(), feedback=Mock(), _submit=Mock())
        desktop_app.BudgetPanel._action(panel, "start")
        panel._submit.assert_called_once_with(("action", 9), desktop_app.run_manager_action, "start", "third")

    def test_manager_passes_explicit_profile_without_shell(self):
        with patch.object(desktop_app.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="OK")) as run:
            desktop_app.run_manager_action("stop", "third")
        self.assertEqual(run.call_args.args[0][-3:], ["stop", "--profile", "third"])

    def test_switch_discards_old_status_and_action_callbacks(self):
        panel = SimpleNamespace(_closed=False, _generation=2, _events=Queue(),
                                _poll_id=None, after=Mock(), _drain_events=Mock(), _render_status=Mock(),
                                _refresh_pending=True, _busy=True)
        panel._events.put((("status", 1), object(), None))
        panel._events.put((("action", 1), None, None))
        with patch.object(desktop_app, "SHOW_REQUEST_FILE") as request:
            request.exists.return_value = False
            desktop_app.BudgetPanel._drain_events(panel)
        panel._render_status.assert_not_called()
        self.assertTrue(panel._busy)
        self.assertTrue(panel._refresh_pending)
