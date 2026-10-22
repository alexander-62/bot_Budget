"""Exercise real Entry edits using generated data, never the user's clipboard."""
from pathlib import Path
from types import SimpleNamespace
import tkinter
import unittest
from unittest.mock import Mock, patch

original_exists = Path.exists
with patch.object(Path, "exists", lambda path: False if path.name == ".env" else original_exists(path)):
    import desktop_app


class DesktopClipboardTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = desktop_app.ctk.CTk()
        except tkinter.TclError as error:
            self.skipTest(str(error))
        self.entry = desktop_app.ctk.CTkEntry(self.root)
        self.entry.pack()
        self.menu = desktop_app.install_entry_editing(self.entry)
        self.native = next(child for child in self.entry.winfo_children() if isinstance(child, tkinter.Entry))
        self.root.update()
        self.native.focus_force()
        self.root.update()
        # Even a regression falling through to the Tk class must only read fake data.
        self.root.tk.call("rename", "::tk::GetSelection", "::budget_original_GetSelection")
        self.root.tk.call("set", "::budget_test_clipboard", "Тестовая вставка")
        self.root.tk.call("proc", "::tk::GetSelection", "w sel", "return $::budget_test_clipboard")

    def tearDown(self):
        self.root.tk.call("rename", "::tk::GetSelection", "")
        self.root.tk.call("rename", "::budget_original_GetSelection", "::tk::GetSelection")
        for callback in self.root.tk.call("after", "info"):
            self.root.after_cancel(callback)
        self.root.destroy()

    def key(self, **kwargs):
        event = dict(widget=self.native, state=4, keycode=86, keysym="v")
        event.update(kwargs)
        with patch.object(desktop_app, "os", SimpleNamespace(name="nt")):
            return desktop_app._entry_edit_keypress(SimpleNamespace(**event))

    def test_native_ctrl_v_replaces_selection_once_and_preserves_unicode(self):
        self.entry.insert(0, "old value")
        self.entry.select_range(0, "end")
        with patch.object(self.native, "clipboard_get", return_value="https://example.test/Таблица") as read:
            # X11 keycodes differ from Windows virtual keys; ask Tk for V on Linux.
            import os
            event = {"keycode": 86} if os.name == "nt" else {"keysym": "v"}
            self.native.event_generate("<KeyPress>", state=4, **event)
            self.root.update()
        read.assert_called_once_with()
        self.assertEqual(self.entry.get(), "https://example.test/Таблица")

    def test_russian_layout_and_shift_insert_paste_in_masked_field(self):
        self.entry.configure(show="•")
        with patch.object(self.native, "clipboard_get", return_value="123:generated_fake"):
            self.assertEqual(self.key(keysym="Cyrillic_em"), "break")
        self.assertEqual(self.entry.get(), "123:generated_fake")
        self.entry.select_range(0, "end")
        with patch.object(self.native, "clipboard_get", return_value="replacement"):
            self.key(state=1, keycode=45, keysym="Insert")
        self.assertEqual(self.entry.get(), "replacement")
        self.assertEqual(self.entry.cget("show"), "•")

    def test_missing_or_empty_clipboard_does_not_delete_selection(self):
        self.entry.insert(0, "keep selected text")
        self.entry.select_range(0, "end")
        with patch.object(self.native, "clipboard_get", side_effect=tkinter.TclError("No text")):
            self.key()
        self.assertEqual(self.entry.get(), "keep selected text")
        with patch.object(self.native, "clipboard_get", return_value=""):
            self.key()
        self.assertEqual(self.entry.get(), "keep selected text")

    def test_disabled_and_readonly_fields_cannot_be_pasted_or_cut(self):
        self.entry.insert(0, "stable-id")
        for state in ("disabled", "readonly"):
            with self.subTest(state=state), patch.object(self.native, "clipboard_get") as read:
                self.native.configure(state=state)
                self.key()
                self.key(keycode=88, keysym="Cyrillic_che")
                read.assert_not_called()
                self.assertEqual(self.entry.get(), "stable-id")

    def test_other_shortcuts_use_native_actions_and_leave_regular_keys_alone(self):
        with patch.object(self.native, "event_generate") as generate:
            for keycode, action in ((65, "<<SelectAll>>"), (67, "<<Copy>>"), (88, "<<Cut>>")):
                self.key(keycode=keycode, keysym="Cyrillic_letter")
                generate.assert_called_with(action)
            count = generate.call_count
            self.assertIsNone(self.key(state=0, keycode=86))
            self.assertIsNone(self.key(state=12, keycode=86))
            self.assertEqual(generate.call_count, count)

    def test_context_menu_pastes_and_disables_mutation_for_locked_fields(self):
        with patch.object(self.menu, "tk_popup"), patch.object(self.menu, "grab_release"), \
             patch.object(self.native, "clipboard_get", return_value="Из меню"):
            self.native.event_generate("<Button-3>", x=2, y=2)
            self.root.update()
            self.assertEqual(self.menu.entrycget(0, "label"), "Вставить")
            self.menu.invoke(0)
            self.assertEqual(self.entry.get(), "Из меню")
            self.native.configure(state="disabled")
            self.native.event_generate("<Button-3>", x=2, y=2)
            self.root.update()
            self.assertEqual(self.menu.entrycget(0, "state"), "disabled")


if __name__ == "__main__":
    unittest.main()
