"""Native process/lock regressions, runnable on Windows without bot credentials."""

from contextlib import ExitStack
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import manage_bot
from services import process_control
from services.process_control import ProcessLock, is_lock_held, is_process_running


class ProcessControlTests(unittest.TestCase):
    def test_live_process_check_does_not_signal_or_stop_process(self):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            for _ in range(3):
                self.assertTrue(is_process_running(child.pid))
                self.assertIsNone(child.poll())
        finally:
            child.terminate()
            child.wait(timeout=5)
        self.assertFalse(is_process_running(child.pid))
        self.assertFalse(is_process_running(0))
        self.assertFalse(is_process_running(-1))

    def test_windows_process_check_uses_wait_handle_not_os_kill(self):
        api = Mock()
        api.OpenProcess.return_value = 123
        api.WaitForSingleObject.return_value = 0x102
        with (
            patch.object(process_control, "IS_WINDOWS", True),
            patch.object(process_control, "_windows_kernel32", return_value=api),
            patch.object(process_control.os, "kill") as kill,
        ):
            self.assertTrue(is_process_running(456))
            api.OpenProcess.assert_called_once_with(0x00100000, False, 456)
            api.WaitForSingleObject.assert_called_once_with(123, 0)
            api.CloseHandle.assert_called_once_with(123)
            kill.assert_not_called()
            api.WaitForSingleObject.return_value = 0  # WAIT_OBJECT_0: exited
            self.assertFalse(is_process_running(456))

    def test_access_denied_is_not_mistaken_for_missing_process(self):
        api = Mock()
        api.OpenProcess.return_value = None
        with (
            patch.object(process_control, "IS_WINDOWS", True),
            patch.object(process_control, "_windows_kernel32", return_value=api),
            patch("ctypes.get_last_error", return_value=5, create=True) as last_error,
        ):
            self.assertTrue(is_process_running(456))
            last_error.return_value = 87  # ERROR_INVALID_PARAMETER: no such PID
            self.assertFalse(is_process_running(456))
            api.CloseHandle.assert_not_called()

    def test_lock_rejects_second_process_and_recovers_after_owner_is_killed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "runtime.lock"
            code = (
                "from pathlib import Path; import sys; "
                "from services.process_control import ProcessLock; "
                "lock = ProcessLock(Path(sys.argv[1])); "
                "print(lock.acquire(), flush=True); sys.stdin.readline()"
            )
            child = subprocess.Popen(
                [sys.executable, "-u", "-c", code, str(path)],
                cwd=manage_bot.BASE_DIR, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            try:
                self.assertEqual(child.stdout.readline().strip(), "True")
                self.assertTrue(is_lock_held(path))
                self.assertFalse(ProcessLock(path).acquire())
            finally:
                child.terminate()
                child.communicate(timeout=5)
            self.assertTrue(path.exists())  # A stale file must not block restart.
            with ProcessLock(path):
                self.assertTrue(is_lock_held(path))
            self.assertFalse(is_lock_held(path))

    def test_near_simultaneous_shortcut_starts_create_only_one_child(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            folder = Path(folder)
            for name, filename in {
                "PID_FILE": ".bot.pid", "PORT_FILE": ".bot.port",
                "LOG_FILE": "bot.log", "START_LOCK_FILE": ".bot-start.lock",
                "BOT_LOCK_FILE": ".bot.lock",
            }.items():
                stack.enter_context(patch.object(manage_bot, name, folder / filename))
            stack.enter_context(patch.object(manage_bot, "_is_running", return_value=True))
            stack.enter_context(patch.object(manage_bot, "_is_webapp_port_busy", return_value=False))
            stack.enter_context(patch.object(manage_bot, "start_tray"))
            stack.enter_context(patch("builtins.print"))
            starting, resume = threading.Event(), threading.Event()
            errors = []

            def spawn(*args, **kwargs):
                if popen.call_count == 1:
                    starting.set()
                    if not resume.wait(5):
                        raise TimeoutError("Test did not resume startup")
                return Mock(pid=4321)

            popen = stack.enter_context(patch.object(manage_bot.subprocess, "Popen", side_effect=spawn))

            def first_start():
                try:
                    manage_bot.start_bot()
                except BaseException as exc:
                    errors.append(exc)

            first = threading.Thread(target=first_start)
            first.start()
            try:
                self.assertTrue(starting.wait(5))
                manage_bot.start_bot()
                self.assertEqual(popen.call_count, 1)
            finally:
                resume.set()
                first.join(timeout=5)
            self.assertFalse(first.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(manage_bot._read_pid(), 4321)
            manage_bot.start_bot()
            self.assertEqual(popen.call_count, 1)

    def test_missing_pid_file_does_not_bypass_held_runtime_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "runtime.lock"
            with (
                ProcessLock(path),
                patch.object(manage_bot, "BOT_LOCK_FILE", path),
                patch.object(manage_bot, "_read_pid", return_value=None),
                patch.object(manage_bot.subprocess, "Popen") as popen,
                patch("builtins.print"),
            ):
                manage_bot._start_bot()
                popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
