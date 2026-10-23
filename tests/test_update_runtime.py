from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from contextlib import ExitStack
import json
import unittest
from unittest.mock import Mock, patch
from services.bot_profiles import BotProfile
from services import update_runtime as update

class RuntimeUpdateTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.base=Path(self.stack.enter_context(TemporaryDirectory()))
        self.profiles=[BotProfile('personal','Personal','sheet1',legacy=True,managed_settings=True),
                       BotProfile('work','Work','sheet2'),BotProfile('off','Off','sheet3',autostart=True)]
        self.alive={101:True,102:True,103:False}
        self.pidmap={p.id:i for p,i in zip(self.profiles,[101,102,103])}
        self.manager=SimpleNamespace(BASE_DIR=self.base,DESKTOP_PID_FILE=self.base/'.desktop.pid',
            TRAY_PID_FILE=self.base/'.tray.pid',DESKTOP_SHOW_FILE=self.base/'.desktop.show',
            EXIT_CODE=0,WEBAPP_HOST='127.0.0.1',stop_tray=Mock(),start_tray=Mock(),start_desktop=Mock())
        def configure(key):
            p=next(p for p in self.profiles if p.id==key)
            self.manager.PROFILE_ID=key
            self.manager.BOT_LOCK_FILE=p.runtime_dir(self.base)/'.bot.lock'
        self.manager.configure_profile=Mock(side_effect=configure)
        self.manager.stop_bot=Mock(side_effect=lambda:self.alive.__setitem__(self.pidmap[self.manager.PROFILE_ID],False))
        self.manager.start_bot=Mock(side_effect=lambda **kw:self.alive.__setitem__(self.pidmap[self.manager.PROFILE_ID],True))
        self.stack.enter_context(patch.object(update,'list_profiles',return_value=self.profiles))
        def pid(path):
            for profile in self.profiles:
                if path==profile.runtime_dir(self.base)/'.bot.pid':return self.pidmap[profile.id]
            return None
        self.stack.enter_context(patch.object(update,'read_int',side_effect=pid))
        self.stack.enter_context(patch.object(update,'is_process_running',side_effect=lambda pid:self.alive.get(pid,False)))
        self.ownership=self.stack.enter_context(patch.object(update,'recorded_process_identity',return_value=True))
        self.ready=self.stack.enter_context(patch.object(update,'wait_ready',return_value={'version':'1.7.1'}))

    def state(self):return json.loads((self.base/update.STATE_FILE).read_text())

    def test_prepare_and_finish_restore_only_previously_running_profiles(self):
        update.prepare(self.manager)
        self.assertEqual(self.state()['profiles'],['personal','work'])
        self.assertFalse(any(self.alive.values()))
        update.finish(self.manager)
        self.assertTrue(self.alive[101]);self.assertTrue(self.alive[102]);self.assertFalse(self.alive[103])
        self.assertFalse((self.base/update.STATE_FILE).exists())
        self.assertEqual([call.args[0].id for call in self.ready.call_args_list],['personal','work'])

    def test_repeated_prepare_keeps_snapshot_after_interrupted_update(self):
        update.prepare(self.manager);update.prepare(self.manager)
        self.assertEqual(self.state()['profiles'],['personal','work'])

    def test_unknown_process_aborts_before_stopping_any_worker(self):
        self.ownership.return_value=False
        with self.assertRaises(RuntimeError):update.prepare(self.manager)
        self.manager.stop_bot.assert_not_called()
        self.assertFalse((self.base/update.STATE_FILE).exists())

    def test_failed_start_keeps_snapshot_but_attempts_other_profiles(self):
        update.prepare(self.manager)
        self.ready.side_effect=[RuntimeError('not ready'),{'version':'1.7.1'}]
        with self.assertRaises(RuntimeError):update.finish(self.manager)
        self.assertEqual(self.manager.start_bot.call_count,2)
        self.assertEqual(self.state()['profiles'],['personal','work'])
        self.ready.side_effect=None
        update.finish(self.manager)
        self.assertFalse((self.base/update.STATE_FILE).exists())

    def test_no_snapshot_does_not_start_any_profile(self):
        update.finish(self.manager)
        self.manager.start_bot.assert_not_called()

class ReadinessTests(unittest.TestCase):
    def test_old_version_never_counts_as_updated(self):
        profile=BotProfile('work','Work','sheet')
        with patch.object(update,'read_int',return_value=101),patch.object(update,'is_process_running',return_value=True), \
             patch.object(update,'read_health',return_value={'profile_id':'work','version':'1.6.3','polling_ready':True,'pid':101}), \
             patch.object(update.time,'monotonic',side_effect=[0,0,36]),patch.object(update.time,'sleep'):
            with self.assertRaises(RuntimeError):update.wait_ready(profile,Path('.'),'localhost','1.7.1')

    def test_venv_child_matches_version_and_os_identity(self):
        profile=BotProfile('work','Work','sheet')
        health={'profile_id':'work','version':'1.7.1','polling_ready':True,'pid':202}
        with patch.object(update,'read_int',return_value=101),patch.object(update,'is_process_running',return_value=True), \
             patch.object(update,'read_health',return_value=health), \
             patch.object(update,'recorded_process_identity',return_value=True),patch.object(update,'is_direct_child',return_value=True):
            self.assertEqual(update.wait_ready(profile,Path('.'),'localhost','1.7.1'),health)

if __name__=='__main__':unittest.main()
