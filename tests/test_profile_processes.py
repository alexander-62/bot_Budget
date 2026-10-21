"""Profile process boundaries, using fake workers and no network calls."""
from contextlib import ExitStack
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import manage_bot
from services import desktop_status
from services.bot_profiles import BotProfile, save_profile
from services.desktop_status import ConnectionStatus
from services.windows_autostart import WindowsAutostart


class ProfileProcessTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.base = Path(self.folder.name)
        profiles = [BotProfile("work", "Work", "sheet-work"), BotProfile("family", "Family", "sheet-family")]
        (self.base / "profiles.json").write_text(json.dumps({"profiles": [asdict(p) for p in profiles]}), encoding="utf-8")
        self.stack = ExitStack()
        for name in ("BASE_DIR", "PROFILE_ID", "EXIT_CODE", "PID_FILE", "PORT_FILE", "LOG_FILE", "BOT_LOCK_FILE", "START_LOCK_FILE"):
            self.stack.enter_context(patch.object(manage_bot, name, getattr(manage_bot, name)))
        manage_bot.BASE_DIR = self.base
        manage_bot.EXIT_CODE = 0
        self.stack.enter_context(patch.object(manage_bot, "process_birth_identity", return_value="fake-birth"))
        self.stack.enter_context(patch("services.process_control.process_birth_identity", side_effect=lambda pid: manage_bot.process_birth_identity(pid)))

    def tearDown(self):
        self.stack.close()
        self.folder.cleanup()

    def test_runtime_paths_locks_and_stop_are_independent(self):
        manage_bot.configure_profile("work")
        work_pid = manage_bot.PID_FILE
        work_lock = manage_bot.BOT_LOCK_FILE
        work_pid.write_text("111", encoding="utf-8")
        manage_bot.configure_profile("family")
        self.assertNotEqual(work_lock, manage_bot.BOT_LOCK_FILE)
        manage_bot.PID_FILE.write_text("222", encoding="utf-8")
        manage_bot.PORT_FILE.write_text("8082", encoding="utf-8")
        with patch.object(manage_bot, "_is_running", return_value=False):
            manage_bot.stop_bot()
        self.assertTrue(work_pid.exists())
        self.assertFalse(manage_bot.PID_FILE.exists())

    def test_fake_workers_start_with_independent_pid_and_port_files(self):
        with patch.object(manage_bot, "_is_running", return_value=True), patch.object(manage_bot, "_is_webapp_port_busy", return_value=False), patch.object(manage_bot, "_format_port_busy_message", return_value="Port reserved."), patch.object(manage_bot, "_is_port_free", return_value=True), patch.object(manage_bot, "is_lock_held", return_value=False), patch.object(manage_bot, "start_tray"), patch.object(manage_bot.subprocess, "Popen", side_effect=[Mock(pid=111), Mock(pid=222)]) as spawn:
            manage_bot.configure_profile("work")
            manage_bot.start_bot()
            work_port = manage_bot._read_port()
            manage_bot.configure_profile("family")
            manage_bot.start_bot()
            self.assertNotEqual(work_port, manage_bot._read_port())
        self.assertEqual((self.base / ".runtime/work/.bot.pid").read_text(encoding="utf-8"), "111")
        self.assertEqual((self.base / ".runtime/family/.bot.pid").read_text(encoding="utf-8"), "222")
        self.assertEqual([call.kwargs["env"]["BOT_BUDGET_PROFILE"] for call in spawn.call_args_list], ["work", "family"])

    def test_child_environment_selects_profile_without_secret_arguments(self):
        manage_bot.configure_profile("work")
        with patch.dict(manage_bot.os.environ, {"BOT_BUDGET_PROFILE": "family"}):
            self.assertEqual(manage_bot._build_runtime_env(8083)["BOT_BUDGET_PROFILE"], "work")
            self.assertNotIn("BOT_BUDGET_PROFILE", manage_bot._shared_runtime_env())

    def test_reused_port_never_borrows_other_profile_health(self):
        runtime = self.base / ".runtime" / "work"
        runtime.mkdir(parents=True)
        (runtime / ".bot.port").write_text("8082", encoding="utf-8")
        with patch.object(desktop_status, "probe_service", return_value=ConnectionStatus(True)), patch.object(
            desktop_status, "read_health", return_value={"ok": True, "pid": 222, "profile_id": "family", "version": "wrong"}
        ), patch.object(desktop_status, "is_process_running", return_value=True):
            result = desktop_status.collect_status(self.base, "localhost", 8080, "installed", "work")
        self.assertEqual(result.state, "stopped")
        self.assertIsNone(result.pid)
        self.assertEqual(result.version, "installed")

    def test_stop_refuses_reused_pid_with_another_profiles_health(self):
        manage_bot.configure_profile("work")
        manage_bot.PID_FILE.write_text("222", encoding="utf-8")
        manage_bot.PORT_FILE.write_text("8082", encoding="utf-8")
        with patch.object(manage_bot, "_is_running", return_value=True), patch("services.desktop_status.read_health", return_value={"ok": True, "pid": 222, "profile_id": "family"}), patch.object(manage_bot.subprocess, "run") as run, patch.object(manage_bot.os, "kill") as kill:
            manage_bot.stop_bot()
        run.assert_not_called()
        kill.assert_not_called()
        self.assertTrue(manage_bot.PID_FILE.exists())

    def test_changed_birth_identity_never_kills_reused_pid(self):
        manage_bot.configure_profile("work")
        manage_bot._write_pid(222)
        manage_bot.PORT_FILE.write_text("8082", encoding="utf-8")
        with patch.object(manage_bot, "process_birth_identity", return_value="different-birth"), patch.object(manage_bot, "_is_running", return_value=True), patch("services.desktop_status.read_health", return_value={}), patch.object(manage_bot.subprocess, "run") as run, patch.object(manage_bot.os, "kill") as kill:
            manage_bot.stop_bot()
        run.assert_not_called()
        kill.assert_not_called()
        self.assertEqual(manage_bot.EXIT_CODE, 1)
        self.assertTrue(manage_bot.PID_FILE.exists())

    def test_matching_birth_identity_can_stop_unresponsive_startup(self):
        manage_bot.configure_profile("work")
        manage_bot._write_pid(222)
        manage_bot.PORT_FILE.write_text("8082", encoding="utf-8")
        with patch.object(manage_bot, "_is_running", return_value=True), patch("services.desktop_status.read_health", return_value={}), patch.object(manage_bot.subprocess, "run", return_value=Mock(returncode=0)) as run, patch.object(manage_bot.os, "kill") as kill:
            manage_bot.stop_bot()
        self.assertEqual(run.call_count + kill.call_count, 1)
        self.assertEqual(manage_bot.EXIT_CODE, 0)
        self.assertFalse(manage_bot.PID_FILE.exists())
        self.assertFalse(manage_bot.PID_FILE.with_name(".bot.identity.json").exists())

    def test_shared_port_lock_surrounds_spawn_and_reservation(self):
        manage_bot.configure_profile("work")
        from services.process_control import is_lock_held
        def fake_start(background):
            self.assertTrue(is_lock_held(self.base / ".ports-start.lock"))
        with patch.object(manage_bot, "_start_bot", side_effect=fake_start):
            manage_bot.start_bot()
        self.assertFalse(is_lock_held(self.base / ".ports-start.lock"))

    def test_concurrent_port_allocators_cannot_spawn_together(self):
        first_entered, second_entered, release = threading.Event(), threading.Event(), threading.Event()
        errors = []
        def fake_start(background):
            if threading.current_thread().name == "first-profile":
                first_entered.set()
                if not release.wait(3):
                    raise TimeoutError("allocator not released")
            else:
                second_entered.set()
        def allocate():
            try:
                manage_bot._start_with_port_reservation(True)
            except BaseException as exc:
                errors.append(exc)
        with patch.object(manage_bot, "_start_bot", side_effect=fake_start):
            first = threading.Thread(target=allocate, name="first-profile")
            second = threading.Thread(target=allocate, name="second-profile")
            first.start()
            try:
                self.assertTrue(first_entered.wait(3))
                second.start()
                self.assertFalse(second_entered.wait(0.1))
            finally:
                release.set()
                first.join(3)
                if second.ident is not None:
                    second.join(3)
        self.assertTrue(second_entered.is_set())
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(errors, [])

    def test_status_refuses_live_pid_with_changed_creation_identity(self):
        manage_bot.configure_profile("work")
        manage_bot._write_pid(222)
        with patch.object(manage_bot, "process_birth_identity", return_value="reused"), patch.object(manage_bot, "_is_running", return_value=True), patch("builtins.print") as output:
            manage_bot.status_bot()
        self.assertEqual(manage_bot.EXIT_CODE, 1)
        self.assertTrue(any("belongs to another process" in str(call) for call in output.call_args_list))

    def test_start_replaces_stale_pid_without_killing_unrelated_process(self):
        manage_bot.configure_profile("work")
        manage_bot._write_pid(222)
        with patch.object(manage_bot, "process_birth_identity", return_value="new-birth"), patch.object(manage_bot, "_is_running", return_value=True), patch.object(manage_bot, "is_lock_held", return_value=False), patch.object(manage_bot, "_is_webapp_port_busy", return_value=False), patch.object(manage_bot, "_profile_port_claimed", return_value=False), patch.object(manage_bot, "start_tray"), patch.object(manage_bot.subprocess, "Popen", return_value=Mock(pid=333)) as spawn, patch.object(manage_bot.os, "kill") as kill:
            manage_bot.start_bot()
        spawn.assert_called_once()
        kill.assert_not_called()
        self.assertEqual(manage_bot._read_pid(), 333)

    def test_unknown_legacy_pid_blocks_start_with_failure(self):
        manage_bot.configure_profile("work")
        manage_bot.PID_FILE.write_text("222", encoding="utf-8")
        with patch.object(manage_bot, "_is_running", return_value=True), patch.object(manage_bot.subprocess, "Popen") as spawn:
            manage_bot.start_bot()
        spawn.assert_not_called()
        self.assertEqual(manage_bot.EXIT_CODE, 1)

    def test_desktop_foreign_health_with_stale_live_pid_is_stopped(self):
        manage_bot.configure_profile("work")
        manage_bot.PID_FILE.write_text("222", encoding="utf-8")
        with patch.object(desktop_status, "probe_service", return_value=ConnectionStatus(True)), patch.object(desktop_status, "read_health", return_value={"ok": True, "pid": 222, "profile_id": "family"}), patch.object(desktop_status, "is_process_running", return_value=True):
            result = desktop_status.collect_status(self.base, "localhost", 8080, "installed", "work")
        self.assertEqual(result.state, "stopped")
        self.assertIsNone(result.pid)

    def test_legacy_personal_health_without_profile_identity_is_owned(self):
        profiles = [BotProfile("personal", "Personal", "", legacy=True)]
        (self.base / "profiles.json").write_text(json.dumps({"profiles": [asdict(p) for p in profiles]}), encoding="utf-8")
        manage_bot.configure_profile("personal")
        manage_bot.PID_FILE.write_text("222", encoding="utf-8")
        manage_bot.PORT_FILE.write_text("8082", encoding="utf-8")
        with patch("services.desktop_status.read_health", return_value={"ok": True, "pid": 222}), patch.object(manage_bot, "_is_running", return_value=True), patch.object(manage_bot.subprocess, "run", return_value=Mock(returncode=0)) as run, patch.object(manage_bot.os, "kill") as kill, patch.object(manage_bot.subprocess, "Popen") as spawn:
            self.assertTrue(manage_bot._worker_identity(222))
            manage_bot.status_bot()
            self.assertEqual(manage_bot.EXIT_CODE, 0)
            manage_bot.start_bot()
            spawn.assert_not_called()
            manage_bot.stop_bot()
        self.assertEqual(run.call_count + kill.call_count, 1)
        self.assertEqual(manage_bot.EXIT_CODE, 0)

    def test_nonlegacy_personal_rejects_health_without_profile_identity(self):
        profiles = [BotProfile("personal", "Personal", "sheet", legacy=False)]
        (self.base / "profiles.json").write_text(json.dumps({"profiles": [asdict(p) for p in profiles]}), encoding="utf-8")
        manage_bot.configure_profile("personal")
        manage_bot.PID_FILE.write_text("222", encoding="utf-8")
        manage_bot.PORT_FILE.write_text("8082", encoding="utf-8")
        with patch("services.desktop_status.read_health", return_value={"ok": True, "pid": 222}):
            self.assertIsNone(manage_bot._worker_identity(222))

    def test_autostart_command_uses_enabled_profile_dispatch(self):
        command = WindowsAutostart(self.base, profiles_mode=True).command
        self.assertIn("start-autostart", command)
        self.assertNotIn("--start-bot", command)

    def test_autostart_starts_only_enabled_profiles(self):
        profiles = [BotProfile("work", "Work", "sheet", autostart=True), BotProfile("family", "Family", "sheet")]
        with patch("services.bot_profiles.list_profiles", return_value=profiles), patch.object(manage_bot, "start_desktop") as panel, patch.object(manage_bot, "configure_profile") as select, patch.object(manage_bot, "start_bot") as start:
            manage_bot.start_autostart()
        panel.assert_called_once_with(minimized=True)
        select.assert_called_once_with("work")
        start.assert_called_once_with()
