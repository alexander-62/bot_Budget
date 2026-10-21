"""Settings saves preserve live workers until validation succeeds."""
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import json
import unittest
from unittest.mock import Mock, patch

import desktop_app as ui
from services import bot_profiles as profiles


class SettingsLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.base = Path(self.stack.enter_context(TemporaryDirectory()))
        self.profile = profiles.BotProfile('work', 'Work', 'sheet-work')
        self.stack.enter_context(patch.object(ui, 'BASE_DIR', self.base))
        self.registry = self.stack.enter_context(patch.object(ui, 'list_profiles', return_value=[self.profile]))
        self.stack.enter_context(patch.object(ui, 'get_profile_token', return_value='123:old'))
        self.validation = self.stack.enter_context(patch.object(ui, 'validate_profile', return_value=ui.ValidationResult(True, 'ok')))
        self.stack.enter_context(patch.object(ui, 'read_int', return_value=111))
        self.stack.enter_context(patch.object(ui, 'is_process_running', return_value=True))
        self.ownership = self.stack.enter_context(patch.object(ui, 'recorded_process_identity', return_value=True))
        self.manager = self.stack.enter_context(patch.object(ui, 'run_manager_action'))
        self.ready = self.stack.enter_context(patch.object(ui, 'wait_for_profile_ready'))
        self.save = self.stack.enter_context(patch.object(ui, 'update_profile', side_effect=lambda candidate, **kw: candidate))

    def apply(self, candidate=None, token=''):
        return ui.save_validated_profile(candidate or self.profile, self.profile, token, Event())

    def test_name_only_saves_without_restart(self):
        result, saved = self.apply(replace(self.profile, name='Renamed'))
        self.assertTrue(result.ok)
        self.assertEqual(saved.name, 'Renamed')
        self.manager.assert_not_called()

    def test_runtime_fields_and_new_token_restart_only_selected_profile(self):
        for field, value in [('spreadsheet_id', 'sheet-new'), ('currency', 'RUB'),
                             ('timezone', 'UTC'), ('credentials_file', 'other.json'),
                             ('track_money_source', True), ('token', '123:new')]:
            with self.subTest(field=field):
                self.manager.reset_mock()
                candidate = replace(self.profile, **{field: value}) if field != 'token' else self.profile
                result, saved = self.apply(candidate, value if field == 'token' else '')
                self.assertTrue(result.ok)
                self.assertEqual(self.manager.call_args_list, [unittest.mock.call('stop', 'work'), unittest.mock.call('start', 'work')])
                self.ready.assert_called_with(candidate)

    def test_unchanged_token_does_not_restart(self):
        self.assertTrue(self.apply(token='123:old')[0].ok)
        self.manager.assert_not_called()

    def test_invalid_connection_leaves_worker_and_settings_untouched(self):
        self.validation.return_value = ui.ValidationResult(False, 'invalid')
        self.assertFalse(self.apply(replace(self.profile, currency='RUB'))[0].ok)
        self.manager.assert_not_called()
        self.save.assert_not_called()

    def test_unowned_live_pid_is_never_stopped(self):
        self.ownership.return_value = False
        self.assertFalse(self.apply(replace(self.profile, currency='RUB'))[0].ok)
        self.manager.assert_not_called()
        self.save.assert_not_called()

    def test_failed_replacement_restores_old_settings_and_worker(self):
        self.ready.side_effect = [RuntimeError('not ready'), None]
        result, saved = self.apply(replace(self.profile, currency='RUB'), '123:new')
        self.assertFalse(result.ok)
        self.assertIsNone(saved)
        self.assertIn('восстановлены', result.message)
        self.assertEqual(self.save.call_args_list[-1], unittest.mock.call(self.profile, token='123:old', base_dir=self.base))
        self.assertEqual([c.args[0] for c in self.manager.call_args_list], ['stop', 'start', 'stop', 'start'])

    def test_failed_save_restarts_original_worker(self):
        self.save.side_effect = OSError('generated failure')
        result, saved = self.apply(replace(self.profile, currency='RUB'))
        self.assertFalse(result.ok)
        self.assertIsNone(saved)
        self.ready.assert_called_once_with(self.profile)

    def test_stale_form_cannot_overwrite_newer_settings(self):
        self.registry.return_value = [replace(self.profile, timezone='UTC')]
        self.assertFalse(self.apply()[0].ok)
        self.save.assert_not_called()
        self.manager.assert_not_called()

    def test_stopped_profile_is_saved_without_starting_it(self):
        with patch.object(ui, 'is_process_running', return_value=False):
            self.assertTrue(self.apply(replace(self.profile, currency='RUB'))[0].ok)
        self.manager.assert_not_called()


class PersonalSettingsTests(unittest.TestCase):
    def test_migration_stores_protected_token_and_preserves_access_and_paths(self):
        with TemporaryDirectory() as directory, patch('services.profile_secrets._crypt', side_effect=lambda data, **kw: data[::-1]):
            base = Path(directory)
            original = profiles.list_profiles(base)[0]
            candidate = replace(original, spreadsheet_id='personal-sheet', credentials_file='common.json', managed_settings=True)
            saved = profiles.update_profile(candidate, token='123:generated', base_dir=base)
            self.assertEqual(profiles.get_profile_token(saved, base), '123:generated')
            self.assertNotIn('123:generated', (base / 'profiles.json').read_text(encoding='utf-8'))
            self.assertTrue(saved.legacy)
            self.assertFalse(saved.uses_legacy_config)
            self.assertEqual(saved.runtime_dir(base), original.runtime_dir(base))
            self.assertEqual(profiles.get_profile('personal', base), candidate)

    def test_running_personal_and_secondary_settings_can_be_opened(self):
        from types import SimpleNamespace
        for profile in (profiles.BotProfile('personal', 'Personal', '', legacy=True), profiles.BotProfile('work', 'Work', 'sheet')):
            panel = SimpleNamespace(_busy=False, _saving_profile=False, selected_profile=profile,
                                    _last_status=SimpleNamespace(pid=111), _show_profile_editor=Mock())
            ui.BudgetPanel._edit_profile(panel)
            panel._show_profile_editor.assert_called_once_with(profile)

if __name__ == '__main__':
    unittest.main()
