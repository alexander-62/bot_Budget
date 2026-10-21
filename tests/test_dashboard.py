from dataclasses import replace
from pathlib import Path
import tkinter
import unittest
from unittest.mock import Mock, patch
import desktop_app
import tray_monitor
from services.bot_profiles import BotProfile
from tests.test_desktop_ui import sample_status

class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.profiles = [BotProfile('personal', 'Personal', 'sheet-a', legacy=True, managed_settings=True),
                         BotProfile('work', 'Work', 'sheet-b', 'RUB')]
        self.guards = [patch.object(desktop_app, 'list_profiles', return_value=self.profiles),
                       patch.object(desktop_app.BudgetPanel, '_submit'),
                       patch.object(desktop_app, 'WindowsAutostart', return_value=Mock(supported=False))]
        for guard in self.guards:
            guard.start(); self.addCleanup(guard.stop)
        try:
            self.panel = desktop_app.BudgetPanel()
        except tkinter.TclError as error:
            self.skipTest(str(error))
        self.panel.update()
        self.addCleanup(self.close_panel)

    def close_panel(self):
        for callback in self.panel.tk.call('after','info'):
            self.panel.after_cancel(callback)
        self.panel._quit()

    def test_all_bot_names_and_statuses_are_visible_without_opening_details(self):
        statuses = {'personal': replace(sample_status(), profile_id='personal'),
                    'work': replace(sample_status(), profile_id='work', state='stopped', pid=None)}
        self.panel._render_dashboard(statuses)
        self.panel.update()
        self.assertFalse(self.panel.detail_panel.winfo_ismapped())
        self.assertFalse(self.panel.profile_menu.winfo_ismapped())
        self.assertEqual(self.panel._profile_cards['personal']['name'].cget('text'), 'Personal')
        self.assertIn('Работает',self.panel._profile_cards['personal']['status'].cget('text'))
        self.assertIn('Остановлен',self.panel._profile_cards['work']['status'].cget('text'))
        for card in self.panel._profile_cards.values():
            self.assertTrue(card['frame'].winfo_ismapped())

    def test_card_expands_selects_correct_bot_and_can_collapse(self):
        self.panel._toggle_card('work')
        self.panel.update()
        self.assertEqual(self.panel.selected_profile.id,'work')
        self.assertTrue(self.panel.detail_panel.winfo_ismapped())
        self.assertEqual(int(self.panel.detail_panel.grid_info()['row']),3)
        self.panel._toggle_card('work')
        self.panel.update()
        self.assertFalse(self.panel.detail_panel.winfo_ismapped())
        self.panel._toggle_card('personal')
        self.assertEqual(int(self.panel.detail_panel.grid_info()['row']),1)

    def test_picture_controls_are_hidden_until_hover_and_hide_after_leaving(self):
        self.panel._toggle_card('personal')
        self.panel.update()
        self.assertFalse(self.panel.picture_controls.winfo_ismapped())
        self.panel._show_picture_controls()
        self.panel.update()
        self.assertTrue(self.panel.picture_controls.winfo_ismapped())
        with patch.object(self.panel,'winfo_pointerxy',return_value=(-100,-100)):
            self.panel._hide_picture_controls()
        self.panel.update()
        self.assertFalse(self.panel.picture_controls.winfo_ismapped())

    def test_refresh_fetches_all_profiles_in_one_background_operation(self):
        self.panel._refresh_pending=False
        self.panel._submit.reset_mock()
        self.panel.refresh()
        self.panel._submit.assert_called_once_with(('dashboard',0),desktop_app.collect_dashboard_statuses,tuple(self.profiles))

class TrayDashboardTests(unittest.TestCase):
    def test_launcher_pid_cannot_suppress_icon_after_os_lock_was_acquired(self):
        tray=tray_monitor.BotTray()
        icon=Mock()
        with patch.object(tray_monitor,'get_bot_status',return_value=('running','ready')), \
             patch.object(tray_monitor,'create_tray_image',return_value=Mock()), \
             patch.object(tray_monitor,'_read_int',return_value=9999), \
             patch.object(tray_monitor,'_is_running',return_value=True), \
             patch.object(tray_monitor,'_write_tray_pid'),patch.object(tray_monitor,'_clear_tray_pid'), \
             patch.object(tray_monitor.pystray,'Icon',return_value=icon):
            self.assertEqual(tray._run_single_instance(),0)
        icon.run.assert_called_once()

    def test_tray_accepts_verified_venv_worker_for_nonlegacy_profile(self):
        profile=BotProfile('work','Work','sheet')
        with patch('services.bot_profiles.list_profiles',return_value=[profile]), \
             patch('services.desktop_status.read_health',return_value={'ok':True,'pid':222,'polling_ready':True}), \
             patch.object(tray_monitor,'_read_int',return_value=111), \
             patch.object(tray_monitor,'_is_running',return_value=True), \
             patch.object(tray_monitor,'recorded_process_identity',return_value=True), \
             patch.object(tray_monitor,'is_direct_child',return_value=True):
            state,tooltip=tray_monitor.get_bot_status()
        self.assertEqual(state,'running')
        self.assertIn('работает',tooltip)

if __name__=='__main__': unittest.main()
