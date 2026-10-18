from contextlib import contextmanager
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

import manage_bot
from services import desktop_status
from services.desktop_status import ConnectionStatus, collect_status, format_uptime, probe_service
from services.process_control import ProcessLock
from services.windows_autostart import RUN_KEY, WindowsAutostart


class DesktopStatusTests(unittest.TestCase):
    def test_reachable_http_error_is_distinct_from_network_and_server_failure(self):
        for error, reachable in [
            (HTTPError("https://test/", 404, "not found", {}, None), True),
            (HTTPError("https://test/", 503, "unavailable", {}, None), False),
            (URLError("network down"), False),
        ]:
            with self.subTest(error=error), patch.object(desktop_status.urllib.request, "urlopen", side_effect=error):
                self.assertEqual(probe_service("https://test/").reachable, reachable)

    def test_status_reads_running_version_and_uptime_from_bot_not_panel(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base / ".bot.pid").write_text("111", encoding="utf-8")
            (base / ".bot.port").write_text("8082", encoding="utf-8")
            with (
                patch.object(desktop_status, "read_health", return_value={
                    "ok": True, "pid": 222, "version": "1.4.3", "uptime_seconds": 125,
                }) as health,
                patch.object(desktop_status, "probe_service", return_value=ConnectionStatus(True, 30)),
                patch.object(desktop_status, "is_process_running", return_value=True) as alive,
            ):
                result = collect_status(base, "127.0.0.1", 8080, "1.5.0")
                health.assert_called_once_with("127.0.0.1", 8082)
                alive.assert_called_once_with(222)
                self.assertEqual((result.state, result.version, result.uptime_seconds), ("running", "1.4.3", 125))
                health.return_value["polling_ready"] = False
                self.assertEqual(collect_status(base, "localhost", 8080, "1.5.0").state, "starting")

    def test_running_process_with_unreachable_service_is_not_shown_as_healthy(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(desktop_status, "read_health", return_value={"ok": True, "pid": 222}),
            patch.object(desktop_status, "probe_service", side_effect=lambda url: ConnectionStatus("google" not in url)),
            patch.object(desktop_status, "is_process_running", return_value=True),
        ):
            self.assertEqual(collect_status(Path(folder), "localhost", 8080, "1.5.0").state, "offline")

    def test_dead_pid_or_unrelated_health_does_not_report_running(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(desktop_status, "read_health", return_value={"ok": True}),
            patch.object(desktop_status, "probe_service", return_value=ConnectionStatus(True)),
        ):
            self.assertEqual(collect_status(Path(folder), "localhost", 8080, "1.5.0").state, "stopped")
        self.assertEqual(format_uptime(3660), "1 ч 01 мин")
        self.assertEqual(format_uptime(None), "—")


class AutostartTests(unittest.TestCase):
    def test_switch_changes_only_its_per_user_registry_value_and_quotes_paths(self):
        values = {}

        @contextmanager
        def key(*args):
            yield "test-key"

        def query(handle, name):
            if name not in values:
                raise FileNotFoundError(name)
            return values[name], 1

        registry = types.SimpleNamespace(
            HKEY_CURRENT_USER="HKCU", REG_SZ=1, KEY_SET_VALUE=2,
            OpenKey=Mock(side_effect=key), CreateKey=Mock(side_effect=key),
            QueryValueEx=Mock(side_effect=query),
            SetValueEx=Mock(side_effect=lambda handle, name, reserved, kind, value: values.__setitem__(name, value)),
            DeleteValue=Mock(side_effect=lambda handle, name: values.pop(name)),
        )
        with (
            tempfile.TemporaryDirectory(prefix="Budget with spaces ") as folder,
            patch.dict(sys.modules, {"winreg": registry}),
            patch("services.windows_autostart.sys.platform", "win32"),
        ):
            startup = WindowsAutostart(Path(folder), str(Path(folder) / "pythonw.exe"))
            self.assertFalse(startup.is_enabled())
            startup.set_enabled(True)
            self.assertTrue(startup.is_enabled())
            self.assertEqual(startup.command, subprocess.list2cmdline([
                str(Path(folder) / "pythonw.exe"), str(Path(folder) / "manage_bot.py"),
                "ui", "--minimized", "--start-bot",
            ]))
            registry.CreateKey.assert_called_once_with("HKCU", RUN_KEY)
            startup.set_enabled(False)
            self.assertFalse(startup.is_enabled())
            self.assertEqual(values, {})


class DesktopLauncherTests(unittest.TestCase):
    def test_opening_existing_panel_sends_show_request_without_second_process(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            with (
                ProcessLock(base / "desktop.lock"),
                patch.object(manage_bot, "DESKTOP_LOCK_FILE", base / "desktop.lock"),
                patch.object(manage_bot, "DESKTOP_START_LOCK_FILE", base / "start.lock"),
                patch.object(manage_bot, "DESKTOP_PID_FILE", base / "desktop.pid"),
                patch.object(manage_bot, "DESKTOP_SHOW_FILE", base / "show"),
                patch.object(manage_bot, "start_tray"),
                patch.object(manage_bot.subprocess, "Popen") as popen,
                patch("builtins.print"),
            ):
                manage_bot.start_desktop()
                self.assertEqual((base / "show").read_text(encoding="utf-8"), "show")
                popen.assert_not_called()
                (base / "show").unlink()
                manage_bot.start_desktop(minimized=True)
                self.assertFalse((base / "show").exists())
                manage_bot.start_desktop(minimized=True, start_bot_on_open=True)
                self.assertEqual((base / "show").read_text(encoding="utf-8"), "start")


if __name__ == "__main__":
    unittest.main()
