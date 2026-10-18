import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

import config
import app
import tray_monitor
from services.process_control import ProcessLock, is_lock_held


class RuntimeSingleInstanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_second_direct_start_is_rejected_before_validation_or_polling(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".bot.lock"
            started, resume = asyncio.Event(), asyncio.Event()

            async def run_bot():
                started.set()
                await resume.wait()

            with (
                patch.object(app, "ProcessLock", side_effect=lambda _: ProcessLock(path)),
                patch.object(app, "_run_bot", AsyncMock(side_effect=run_bot)) as run,
            ):
                first = asyncio.create_task(app.main())
                try:
                    await asyncio.wait_for(started.wait(), 2)
                    await asyncio.wait_for(app.main(), 2)
                    run.assert_awaited_once()
                    self.assertTrue(is_lock_held(path))
                finally:
                    resume.set()
                    await first
            self.assertFalse(is_lock_held(path))

    async def test_failed_start_releases_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".bot.lock"
            with (
                patch.object(app, "ProcessLock", side_effect=lambda _: ProcessLock(path)),
                patch.object(app, "_run_bot", AsyncMock(side_effect=RuntimeError("startup failed"))),
            ):
                with self.assertRaisesRegex(RuntimeError, "startup failed"):
                    await app.main()
            self.assertFalse(is_lock_held(path))

    async def test_second_tray_instance_is_rejected_and_failure_releases_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".tray.lock"
            tray = tray_monitor.BotTray()
            with (
                patch.object(tray_monitor, "TRAY_LOCK_FILE", path),
                patch.object(tray, "_run_single_instance", Mock(return_value=0)) as run,
            ):
                with ProcessLock(path):
                    self.assertEqual(tray.run(), 0)
                    run.assert_not_called()
                self.assertEqual(tray.run(), 0)
                run.assert_called_once()
                run.side_effect = RuntimeError("tray failed")
                with self.assertRaisesRegex(RuntimeError, "tray failed"):
                    tray.run()
                self.assertFalse(is_lock_held(path))


if __name__ == "__main__":
    unittest.main()
