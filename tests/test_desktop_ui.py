from datetime import datetime
from dataclasses import replace
import os
from pathlib import Path
import time
import tkinter
import unittest
from unittest.mock import Mock, patch

import config
from aiohttp.test_utils import make_mocked_request
import app
import desktop_app
from services.desktop_status import ConnectionStatus, DesktopStatus


def sample_status():
    return DesktopStatus(
        state="running", pid=123, version="1.5.0", uptime_seconds=7260,
        telegram=ConnectionStatus(True, 42), google=ConnectionStatus(True, 67),
        checked_at=datetime(2026, 10, 18, 18, 42, 0),
    )


class HealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_health_reports_actual_process_version_and_uptime(self):
        webapp = app.create_web_app()
        handler = next(route.handler for route in webapp.router.routes()
                       if route.method == "GET" and route.resource.canonical == "/webapp/health")
        response = await handler(make_mocked_request("GET", "/webapp/health"))
        import json
        payload = json.loads(response.text)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["pid"], os.getpid())
        self.assertEqual(payload["version"], app.__version__)
        self.assertGreaterEqual(payload["uptime_seconds"], 0)
        self.assertFalse(payload["polling_ready"])
        webapp[app.RUNTIME_STATE_KEY]["polling_ready"] = True
        response = await handler(make_mocked_request("GET", "/webapp/health"))
        self.assertTrue(json.loads(response.text)["polling_ready"])


class DesktopUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            probe = tkinter.Tk()
            probe.withdraw()
            probe.destroy()
        except tkinter.TclError as exc:
            raise unittest.SkipTest(f"A desktop display is required: {exc}")

    def setUp(self):
        self.worker_patch = patch.object(desktop_app.BudgetPanel, "_submit")
        self.worker_patch.start()
        self.autostart = Mock(supported=True)
        self.autostart.is_enabled.return_value = False
        self.startup_patch = patch.object(desktop_app, "WindowsAutostart", return_value=self.autostart)
        self.startup_patch.start()
        self.panel = desktop_app.BudgetPanel()
        self.panel.update()

    def tearDown(self):
        if not self.panel._closed:
            # CTk's global appearance/DPI timers otherwise outlive each test root.
            for callback in self.panel.tk.call("after", "info"):
                self.panel.after_cancel(callback)
            self.panel._quit()
        self.worker_patch.stop()
        self.startup_patch.stop()

    def test_panel_renders_existing_logo_status_and_controls(self):
        self.panel._render_status(sample_status())
        self.panel.update()
        self.assertIsNotNone(self.panel.logo_image)
        self.assertEqual(self.panel.headline.cget("text"), "Бот работает")
        self.assertIn("2 ч 01 мин", self.panel.uptime_label.cget("text"))
        self.assertEqual(self.panel.action_buttons["start"].cget("state"), "disabled")
        self.assertEqual(self.panel.action_buttons["stop"].cget("state"), "normal")
        screenshot = os.getenv("BOT_BUDGET_UI_SCREENSHOT")
        if screenshot:
            from PIL import ImageGrab
            self.panel.lift()
            self.panel.update()
            time.sleep(0.2)
            path = Path(screenshot)
            path.parent.mkdir(parents=True, exist_ok=True)
            x, y = self.panel.winfo_rootx(), self.panel.winfo_rooty()
            ImageGrab.grab(bbox=(x, y, x + self.panel.winfo_width(), y + self.panel.winfo_height())).save(path)

    def test_close_hides_and_reopen_shows_same_window(self):
        with patch.object(self.panel, "_tray_available", return_value=True):
            self.panel._hide()
        self.assertEqual(self.panel.state(), "withdrawn")
        self.assertFalse(self.panel._closed)
        self.panel.show_panel()
        self.panel.update()
        self.assertEqual(self.panel.state(), "normal")

    def test_autostart_switch_does_not_leave_false_success_after_error(self):
        self.panel.autostart_var.set(True)
        self.panel._toggle_autostart()
        self.autostart.set_enabled.assert_called_once_with(True)
        self.autostart.set_enabled.side_effect = OSError("access denied")
        self.panel.autostart_var.set(False)
        self.panel._toggle_autostart()
        self.assertTrue(self.panel.autostart_var.get())
        self.assertIn("Не удалось", self.panel.feedback.cget("text"))

    def test_automatic_start_waits_for_services_then_submits_one_start(self):
        stopped = replace(sample_status(), state="stopped", pid=None, uptime_seconds=None)
        self.panel._startup_requested = True
        self.panel._render_status(replace(stopped, telegram=ConnectionStatus(False)))
        self.assertFalse(self.panel._busy)
        self.assertTrue(self.panel._startup_requested)
        self.panel._submit.reset_mock()
        self.panel._render_status(stopped)
        self.assertTrue(self.panel._busy)
        self.assertFalse(self.panel._startup_requested)
        self.panel._submit.assert_called_once_with("action", desktop_app.run_manager_action, "start")


if __name__ == "__main__":
    unittest.main()
