"""Profile-specific picture display and asynchronous save routing, no network."""
from dataclasses import replace
from pathlib import Path
import tempfile
import tkinter
import unittest
from unittest.mock import Mock, patch

from PIL import Image

original_exists = Path.exists
with patch.object(Path, "exists", lambda path: False if path.name == ".env" else original_exists(path)):
    import desktop_app
from services.bot_profiles import BotProfile
from services.profile_images import import_profile_image


class ProfilePictureUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            root = tkinter.Tk()
            root.destroy()
        except tkinter.TclError as error:
            raise unittest.SkipTest(str(error))

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.base = Path(self.folder.name)
        paths = []
        for name, color in (("red", "red"), ("blue", "blue"), ("logo", "green")):
            path = self.base / (name + ".png")
            with Image.new("RGB", (80, 80), color) as image:
                image.save(path)
            if name != "logo":
                paths.append(import_profile_image(path, self.base))
        self.personal = BotProfile("personal", "Personal", "", legacy=True, image_file=paths[0])
        self.business = BotProfile("business", "Business", "sheet", "RUB", track_money_source=True, image_file=paths[1])
        self.registry = [self.personal, self.business]
        self.patches = [
            patch.object(desktop_app, "BASE_DIR", self.base),
            patch.object(desktop_app, "list_profiles", side_effect=lambda _: list(self.registry)),
            patch.object(desktop_app, "WindowsAutostart", return_value=Mock(supported=False)),
            patch.object(desktop_app.BudgetPanel, "_submit"),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.panel = desktop_app.BudgetPanel()

    def tearDown(self):
        if self.panel._editor is not None and self.panel._editor.winfo_exists():
            self.panel._editor.destroy()
        for callback in self.panel.tk.call("after", "info"):
            self.panel.after_cancel(callback)
        self.panel._quit()

    def pixel(self):
        return self.panel.logo_image.cget("light_image").getpixel((60, 60))

    def test_switch_changes_only_selected_picture_and_clear_restores_default(self):
        self.assertEqual(self.pixel(), (255, 0, 0, 255))
        self.panel._select_profile(self.panel._profile_label(self.business))
        self.assertEqual(self.panel.profile_menu.get(), self.panel._profile_label(self.business))
        self.assertEqual(self.pixel(), (0, 0, 255, 255))
        cleared = replace(self.business, image_file="")
        self.registry = [self.personal, cleared]
        self.panel._finish_picture_save(cleared, None)
        self.assertEqual(self.pixel(), (0, 128, 0, 255))
        self.assertTrue(self.panel.selected_profile.track_money_source)
        self.panel._select_profile(self.panel._profile_label(self.personal))
        self.assertEqual(self.pixel(), (255, 0, 0, 255))

    def test_native_picker_cancel_and_save_are_scoped_to_selected_profile(self):
        self.panel._select_profile(self.panel._profile_label(self.business))
        self.panel._submit.reset_mock()
        with patch.object(desktop_app.filedialog, "askopenfilename", return_value=""):
            self.panel._choose_profile_picture()
        self.panel._submit.assert_not_called()
        selected = str(self.base / "red.png")
        with patch.object(desktop_app.filedialog, "askopenfilename", return_value=selected):
            self.panel._choose_profile_picture()
        self.panel._submit.assert_called_once_with("picture", desktop_app.save_profile_picture, "business", selected)
        self.assertTrue(self.panel._picture_busy)
        self.assertEqual(self.panel.picture_button.cget("state"), "disabled")

    def test_late_completion_does_not_replace_new_selection_or_photo(self):
        self.panel._picture_busy = True
        self.panel._select_profile(self.panel._profile_label(self.business))
        self.panel._finish_picture_save(self.personal, None)
        self.assertEqual(self.panel.selected_profile.id, "business")
        self.assertEqual(self.pixel(), (0, 0, 255, 255))
        self.assertFalse(self.panel._picture_busy)

    def test_native_dialog_keeps_original_target_if_selection_changes(self):
        selected = str(self.base / "red.png")
        def choose(**kwargs):
            self.panel._select_profile(self.panel._profile_label(self.business))
            return selected
        with patch.object(desktop_app.filedialog, "askopenfilename", side_effect=choose):
            self.panel._choose_profile_picture()
        self.assertEqual(self.panel._submit.call_args.args, ("picture", desktop_app.save_profile_picture, "personal", selected))

    def test_open_form_or_saving_picture_prevents_stale_metadata_overwrite(self):
        self.panel._show_profile_editor(self.business)
        with patch.object(desktop_app.filedialog, "askopenfilename") as choose:
            self.panel._choose_profile_picture()
        choose.assert_not_called()
        self.panel._editor.destroy()
        self.panel._picture_busy = True
        with patch.object(desktop_app, "update_profile") as save:
            self.panel.profile_autostart_var.set(True)
            self.panel._toggle_profile_autostart()
        save.assert_not_called()
        self.assertFalse(self.panel.profile_autostart_var.get())

    def test_save_failure_keeps_photo_and_actual_helper_needs_no_token(self):
        original = self.pixel()
        self.panel._finish_picture_save(None, ValueError("invalid image"))
        self.assertEqual(self.pixel(), original)
        with patch.object(desktop_app, "validate_profile", side_effect=AssertionError("No network validation")), \
             patch("services.bot_profiles.load_token", side_effect=AssertionError("No tokens")):
            saved = desktop_app.save_profile_picture("personal", self.base / "blue.png", base_dir=self.base)
        self.assertTrue(saved.image_file.startswith(".profile-images/"))
        self.assertTrue(saved.legacy)


if __name__ == "__main__":
    unittest.main()
