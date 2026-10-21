"""Small Windows control panel; Telegram and Sheets stay in the bot process."""

import argparse
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import logging
import os
from pathlib import Path
from queue import Empty, Queue
from threading import Event
import subprocess
import sys
import time
import webbrowser
from tkinter import filedialog, Menu, TclError

from config import WEBAPP_HOST, WEBAPP_PORT
import customtkinter as ctk
from PIL import Image, ImageTk

from services.desktop_status import DesktopStatus, collect_status, format_uptime, read_int
from services.process_control import ProcessLock, is_process_running, recorded_process_identity, is_direct_child
from services.windows_autostart import WindowsAutostart
from services.bot_profiles import BotProfile, list_profiles, get_profile_token, save_profile, update_profile, set_profile_image
from services.profile_images import import_profile_image, load_profile_image
from services.profile_validation import ValidationResult, validate_profile, normalize_spreadsheet_id
from version import __version__


BASE_DIR = Path(__file__).resolve().parent
DESKTOP_PID_FILE = BASE_DIR / ".desktop.pid"
SHOW_REQUEST_FILE = BASE_DIR / ".desktop.show"
REFRESH_SECONDS = 10
BG, CARD, BORDER = "#111319", "#1B1E27", "#2B303D"
TEXT, MUTED, ACCENT = "#F4F4F6", "#9A9FAF", "#F2B2BE"
GREEN, AMBER, RED = "#65D6A5", "#E9BF77", "#F08D95"
UI_FONT = "Segoe UI" if os.name == "nt" else "DejaVu Sans"


def run_manager_action(command: str, profile_id: str = "personal") -> str:
    if command not in {"start", "stop", "restart"}:
        raise ValueError("Неизвестная команда управления.")
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(
        [sys.executable, str(BASE_DIR / "manage_bot.py"), command, "--profile", profile_id],
        cwd=BASE_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", timeout=30, check=False, **kwargs,
    )
    if result.returncode:
        raise RuntimeError("Команда не выполнена. Подробности — в bot.log.")
    return result.stdout.strip()


def collect_dashboard_statuses(profiles):
    def collect(profile):
        return collect_status(BASE_DIR, WEBAPP_HOST, WEBAPP_PORT, __version__, profile_id=profile.id)
    with ThreadPoolExecutor(max_workers=min(4, max(1, len(profiles)))) as executor:
        return dict(zip((profile.id for profile in profiles), executor.map(collect, profiles)))


def editable_profile(profile):
    """Import old personal settings in memory; secrets never enter form fields."""
    if not profile or not profile.uses_legacy_config:
        return profile
    import config
    return replace(profile, spreadsheet_id=config.SPREADSHEET_ID,
                   credentials_file=config.GOOGLE_CREDENTIALS_FILE,
                   managed_settings=True)


def runtime_settings_changed(candidate, original, token):
    if original is None:
        return False
    effective = editable_profile(original)
    fields = ("spreadsheet_id", "currency", "timezone", "credentials_file", "track_money_source")
    return any(getattr(candidate, key) != getattr(effective, key) for key in fields) or bool(
        token and token != get_profile_token(original, BASE_DIR))


def wait_for_profile_ready(profile, timeout=20):
    from services.desktop_status import read_health
    runtime = profile.runtime_dir(BASE_DIR)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pid = read_int(runtime / ".bot.pid")
        port = read_int(runtime / ".bot.port")
        if pid and port:
            health = read_health(WEBAPP_HOST, port)
            endpoint_pid = health.get("pid")
            if (health.get("profile_id") == profile.id and health.get("polling_ready") is True
                    and recorded_process_identity(runtime, pid, profile.id) is True
                    and isinstance(endpoint_pid, int)
                    and (endpoint_pid == pid or is_direct_child(endpoint_pid, pid))):
                return
        time.sleep(0.2)
    raise RuntimeError("Бот не подтвердил готовность после перезапуска.")


def save_validated_profile(candidate, original, token, cancelled):
    old_token = get_profile_token(original, BASE_DIR) if original else ""
    actual_token = token or old_token
    result = validate_profile(candidate, actual_token, profiles=list_profiles(BASE_DIR),
                              token_loader=lambda p: get_profile_token(p, BASE_DIR))
    if not result.ok or cancelled.is_set():
        return result, None
    runtime = candidate.runtime_dir(BASE_DIR)
    runtime.mkdir(parents=True, exist_ok=True)
    restart = runtime_settings_changed(candidate, original, token)
    migration = bool(original and original.uses_legacy_config and not candidate.uses_legacy_config)
    saved = None
    stopped = False
    start_lock = ProcessLock(runtime / ".bot-start.lock")
    bot_lock = ProcessLock(runtime / ".bot.lock")
    try:
        if not start_lock.acquire():
            return ValidationResult(False, "Бот запускается. Повторите сохранение через несколько секунд."), None
        if original:
            current = next((p for p in list_profiles(BASE_DIR) if p.id == original.id), None)
            if current != original:
                return ValidationResult(False, "Настройки уже изменились. Откройте форму заново."), None
        pid = read_int(runtime / ".bot.pid")
        running = bool(pid and is_process_running(pid))
        if running:
            if original is None or recorded_process_identity(runtime, pid, candidate.id) is not True:
                return ValidationResult(False, "Не удалось подтвердить процесс бота. Обновите статус и повторите сохранение."), None
            if restart:
                if cancelled.is_set():
                    return result, None
                run_manager_action("stop", candidate.id)
                stopped = True
        if not running or stopped:
            deadline = time.monotonic() + 5
            while not bot_lock.acquire():
                if time.monotonic() >= deadline:
                    raise RuntimeError("Процесс ещё останавливается.")
                time.sleep(0.05)
        if cancelled.is_set() and not stopped:
            return result, None
        function = update_profile if original else save_profile
        saved = function(candidate, token=(actual_token if migration else token or None), base_dir=BASE_DIR)
    except Exception:
        result = ValidationResult(False, "Не удалось сохранить настройки. Прежние настройки сохранены.")
    finally:
        bot_lock.release()
        start_lock.release()
    if stopped:
        try:
            run_manager_action("start", candidate.id)
            wait_for_profile_ready(saved or original)
        except Exception:
            # Undo the committed configuration if the replacement cannot start.
            if saved:
                try:
                    run_manager_action("stop", candidate.id)
                    update_profile(original, token=None if original.uses_legacy_config else old_token, base_dir=BASE_DIR)
                    run_manager_action("start", original.id)
                    wait_for_profile_ready(original)
                    return ValidationResult(False, "Новые настройки не запустились. Прежние настройки восстановлены, бот снова работает."), None
                except Exception:
                    return ValidationResult(False, "Ошибка перезапуска или восстановления. Проверьте состояние бота и его журнал."), saved
            return ValidationResult(False, "Настройки не сохранены; не удалось запустить бота заново. Проверьте журнал."), None
    if saved:
        message = "Настройки сохранены. Бот перезапущен." if stopped else "Настройки сохранены без перезапуска."
        return ValidationResult(True, message), saved
    return result, None


def save_profile_picture(profile_id, path, base_dir=None):
    base_dir = BASE_DIR if base_dir is None else base_dir
    image_file = import_profile_image(Path(path), base_dir) if path else ""
    return set_profile_image(profile_id, image_file, base_dir=base_dir)


def _entry_edit_action(target, action):
    """Handle explicit user edits without logging or retaining clipboard data."""
    if target is None:
        return "break"
    try:
        state = str(target.cget("state"))
        if state == "disabled" or (state != "normal" and action in {"paste", "cut"}):
            return "break"
        if action == "paste":
            # Read first: an unavailable/empty clipboard must not delete selection.
            text = target.clipboard_get()
            if text:
                if target.selection_present():
                    target.delete("sel.first", "sel.last")
                target.insert("insert", text)
                target.xview("insert")
        elif action in {"copy", "cut", "all"}:
            target.event_generate({"copy": "<<Copy>>", "cut": "<<Cut>>", "all": "<<SelectAll>>"}[action])
    except TclError:
        # Clipboard can be empty or contain a non-text format; keep the field.
        pass
    return "break"


def _entry_edit_keypress(event):
    state = int(event.state)
    if state & (0x8 | 0x20000):  # Alt/AltGr is not a clipboard shortcut.
        return None
    if state & 0x4:
        # Windows virtual key codes stay stable when English/Russian changes.
        action = ({65: "all", 67: "copy", 86: "paste", 88: "cut"}.get(event.keycode)
                  if os.name == "nt" else {"a": "all", "c": "copy", "v": "paste", "x": "cut"}.get(event.keysym.lower()))
        if action:
            return _entry_edit_action(event.widget, action)
    elif state & 0x1 and event.keysym == "Insert":
        return _entry_edit_action(event.widget, "paste")
    return None


def install_entry_editing(entry):
    """CTkEntry.bind forwards to its native Entry before Tk class bindings."""
    menu = Menu(entry, tearoff=False)
    current = {"target": None}
    for label, action in (("Вставить", "paste"), ("Копировать", "copy"),
                          ("Вырезать", "cut"), ("Выделить всё", "all")):
        menu.add_command(label=label, command=lambda action=action: _entry_edit_action(current["target"], action))

    def popup(event, keyboard=False):
        target = current["target"] = event.widget
        target.focus_set()
        state = str(target.cget("state"))
        selected = bool(target.selection_present())
        for index, enabled in enumerate((state == "normal", selected and state != "disabled",
                                         selected and state == "normal", state != "disabled")):
            menu.entryconfigure(index, state="normal" if enabled else "disabled")
        x = target.winfo_rootx() + 12 if keyboard else event.x_root
        y = target.winfo_rooty() + target.winfo_height() if keyboard else event.y_root
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()
        return "break"

    entry.bind("<KeyPress>", _entry_edit_keypress, add="+")
    entry.bind("<Button-3>", popup, add="+")
    entry.bind("<Menu>", lambda event: popup(event, True), add="+")
    entry.bind("<Shift-F10>", lambda event: popup(event, True), add="+")
    return menu


class BudgetPanel(ctk.CTk):
    def __init__(self, *, minimized: bool = False, start_bot: bool = False):
        ctk.set_appearance_mode("dark")
        if os.name != "nt":
            ctk.DrawEngine.preferred_drawing_method = "polygon_shapes"
        super().__init__(fg_color=BG)
        self.title("Bot Budget — панель управления")
        # CTk sizes are logical pixels; fit both small screens and Windows DPI.
        scale = self._get_window_scaling()
        width = min(880, int((self.winfo_screenwidth() - 60) / scale))
        height = min(790, int((self.winfo_screenheight() - 100) / scale))
        self.geometry(f"{width}x{height}+20+20")
        self.minsize(min(820, width), min(740, height))
        self.protocol("WM_DELETE_WINDOW", self._hide)
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="BudgetPanel")
        self._events = Queue()
        self._closed = False
        self._refresh_pending = False
        self._busy = False
        self._startup_requested = start_bot
        self._refresh_again = False
        self._last_status = None
        try:
            self.profiles = list_profiles(BASE_DIR)
        except ValueError as error:
            from tkinter import messagebox
            messagebox.showerror("Не удалось открыть профили", str(error), parent=self)
            self._executor.shutdown(wait=False, cancel_futures=True)
            self.destroy()
            return
        self.selected_profile = self.profiles[0]
        self._generation = 0
        self._profile_statuses = {}
        self._dashboard_statuses = {}
        self._expanded_profile = None
        self._profile_cards = {}
        self._editor = None
        self._picture_busy = False
        self._autostart = WindowsAutostart(BASE_DIR, profiles_mode=True)
        self._build_ui()
        self._set_icon()
        self._poll_id = self.after(150, self._drain_events)
        self._refresh_id = self.after(REFRESH_SECONDS * 1000, self._scheduled_refresh)
        if minimized:
            self.withdraw()
            self.after(1500, self._keep_accessible)
        self.refresh()

    def _label(self, parent, text, size=14, color=TEXT, bold=False, **kwargs):
        return ctk.CTkLabel(
            parent, text=text, text_color=color, height=kwargs.pop("height", 0),
            font=ctk.CTkFont(family=UI_FONT, size=size, weight="bold" if bold else "normal"),
            **kwargs,
        )

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=30, pady=(16, 12))
        self._label(header, "Bot Budget", 27, bold=True).pack(side="left")
        self._label(header, "ПАНЕЛЬ УПРАВЛЕНИЯ", 11, MUTED).pack(side="left", padx=18, pady=(6, 0))
        self._label(header, "●  Локально", 12, MUTED).pack(side="right", pady=(6, 0))

        body = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0, scrollbar_button_color=BORDER)
        body.grid(row=1, column=0, sticky="nsew", padx=30)
        self._dashboard_scroll = body
        body.grid_columnconfigure(0, weight=1)
        toolbar = ctk.CTkFrame(body, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        self.dashboard_summary = self._label(toolbar, "Ваши боты · проверяем состояние", 14, MUTED)
        self.dashboard_summary.pack(side="left")
        ctk.CTkButton(toolbar, text="+ Добавить бота", width=145, height=36,
                      command=self._add_profile).pack(side="right")
        self.dashboard = ctk.CTkFrame(body, fg_color="transparent")
        self.dashboard.grid(row=1, column=0, sticky="ew")
        self.dashboard.grid_columnconfigure(0, weight=1)
        # Retain selection state for editor callbacks; navigation uses cards.
        self.profile_menu = ctk.CTkOptionMenu(toolbar, values=self._profile_labels(), command=self._select_profile)
        self.detail_panel = body = ctk.CTkFrame(self.dashboard, fg_color="transparent")
        body.grid_columnconfigure(0, weight=1)
        self._sync_profile_cards()
        detail_toolbar = ctk.CTkFrame(body, fg_color="transparent")
        detail_toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self._label(detail_toolbar, "Управление ботом", 15, MUTED).pack(side="left")
        self.edit_button = ctk.CTkButton(detail_toolbar, text="Настройки", width=110, command=self._edit_profile)
        self.edit_button.pack(side="right")
        content = ctk.CTkFrame(body, fg_color="transparent")
        content.grid(row=1, column=0, sticky="ew")
        content.grid_columnconfigure(0, weight=1)
        body = content

        hero = ctk.CTkFrame(body, fg_color=CARD, corner_radius=22, border_width=1, border_color=BORDER)
        hero.grid(row=0, column=0, sticky="ew")
        hero.grid_columnconfigure(0, weight=1)
        self.badge = self._label(hero, "●  Проверяем состояние", 12, MUTED)
        self.badge.grid(row=0, column=0, sticky="w", padx=26, pady=(23, 5))
        self.headline = self._label(hero, "Бот под контролем", 30, bold=True, anchor="w")
        self.headline.grid(row=1, column=0, sticky="w", padx=26)
        self.description = self._label(hero, "Сейчас проверим процесс и доступность сервисов.", 13, MUTED)
        self.description.grid(row=2, column=0, sticky="w", padx=26, pady=(3, 12))
        stats = ctk.CTkFrame(hero, fg_color="transparent")
        stats.grid(row=3, column=0, sticky="w", padx=26, pady=(0, 24))
        self.version_label = self._label(stats, f"Бот  {__version__}", 12, MUTED)
        self.version_label.pack(side="left")
        self._label(stats, "   /   ", 12, BORDER).pack(side="left")
        self.uptime_label = self._label(stats, "В работе  —", 12, MUTED)
        self.uptime_label.pack(side="left")
        logo_card = ctk.CTkFrame(hero, width=172, height=194, fg_color="#FFFFFF", corner_radius=20)
        logo_card.grid(row=0, column=1, rowspan=4, padx=(18, 24), pady=24)
        logo_card.grid_propagate(False)
        logo_card.grid_rowconfigure(0, weight=1)
        logo_card.grid_columnconfigure(0, weight=1)
        self.logo_label = self._label(logo_card, "", 60, "#9A5868", bold=True)
        self.logo_label.grid(row=0, column=0, pady=(6, 0))
        self.logo_card = logo_card
        picture_controls = self.picture_controls = ctk.CTkFrame(logo_card, fg_color="transparent")
        self.picture_button = ctk.CTkButton(picture_controls, text="Картинка", width=76, height=26,
                                          fg_color=CARD, command=self._choose_profile_picture)
        self.picture_button.pack(side="left", padx=(0, 3))
        self.picture_reset_button = ctk.CTkButton(picture_controls, text="Сбросить", width=76, height=26,
                                                fg_color=CARD, command=self._clear_profile_picture)
        self.picture_reset_button.pack(side="left")
        for widget in (logo_card, self.logo_label, picture_controls, self.picture_button, self.picture_reset_button):
            widget.bind("<Enter>", self._show_picture_controls, add="+")
            widget.bind("<Leave>", self._schedule_picture_hide, add="+")
        self._picture_hide_id = None
        self._render_profile_image()

        self._label(body, "Подключения", 16, bold=True).grid(row=1, column=0, sticky="w", pady=(20, 10))
        network = ctk.CTkFrame(body, fg_color="transparent")
        network.grid(row=2, column=0, sticky="ew")
        network.grid_columnconfigure((0, 1), weight=1, uniform="network")
        self.connection_widgets = {}
        for col, (key, title, detail) in enumerate([
            ("telegram", "Telegram", "Доступность Telegram API"),
            ("google", "Google Sheets", "Доступность Google API"),
        ]):
            tile = ctk.CTkFrame(network, fg_color=CARD, corner_radius=16, border_width=1, border_color=BORDER)
            tile.grid(row=0, column=col, sticky="ew", padx=(0, 7) if col == 0 else (7, 0))
            tile.grid_columnconfigure(0, weight=1)
            self._label(tile, title, 16, bold=True).grid(row=0, column=0, sticky="w", padx=20, pady=(16, 1))
            status = self._label(tile, "●  Проверяем…", 12, MUTED)
            status.grid(row=1, column=0, sticky="w", padx=20, pady=(1, 5))
            self._label(tile, detail, 11, MUTED).grid(row=2, column=0, sticky="w", padx=20, pady=(0, 16))
            self.connection_widgets[key] = status
        self._label(body, "Проверяем связь с сервисами. Доступ к вашей таблице проверяет сам бот.", 11, MUTED).grid(
            row=3, column=0, sticky="w", pady=(7, 0),
        )

        controls = ctk.CTkFrame(body, fg_color="transparent")
        controls.grid(row=4, column=0, sticky="ew", pady=(23, 12))
        controls.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="buttons")
        self.action_buttons = {}
        for col, (command, title) in enumerate([
            ("start", "Запустить"), ("restart", "Перезапустить"), ("stop", "Остановить"), ("log", "Открыть лог"),
        ]):
            button = ctk.CTkButton(
                controls, text=title, height=42, corner_radius=11,
                fg_color=ACCENT if command == "start" else CARD,
                hover_color="#DFA1AE" if command == "start" else "#282D3A",
                text_color=BG if command == "start" else RED if command == "stop" else TEXT,
                font=ctk.CTkFont(family=UI_FONT, size=13, weight="bold"),
                border_width=0 if command == "start" else 1, border_color=BORDER,
                command=self._open_log if command == "log" else lambda cmd=command: self._action(cmd),
            )
            button.grid(row=0, column=col, sticky="ew", padx=(0, 8) if col < 3 else 0)
            if command != "log":
                self.action_buttons[command] = button

        preferences = ctk.CTkFrame(body, fg_color=CARD, corner_radius=16)
        preferences.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        preferences.grid_columnconfigure(0, weight=1)
        self.profile_autostart_var = ctk.BooleanVar(value=self.selected_profile.autostart)
        self.profile_autostart_switch = ctk.CTkSwitch(preferences, text="Включать выбранного бота при входе", variable=self.profile_autostart_var, command=self._toggle_profile_autostart)
        self.profile_autostart_switch.grid(row=2, column=0, columnspan=2, sticky="w", padx=20, pady=(0, 18))
        ctk.CTkButton(preferences, text="Открыть таблицу выбранного бота", command=self._open_spreadsheet).grid(row=3, column=0, columnspan=2, sticky="ew", padx=20, pady=(0, 18))
        self._label(preferences, "Запускать вместе с Windows", 14, bold=True).grid(
            row=0, column=0, sticky="w", padx=20, pady=(17, 0),
        )
        self._label(preferences, "Отмеченные боты включатся при входе в Windows.", 12, MUTED).grid(
            row=1, column=0, sticky="w", padx=20, pady=(2, 18),
        )
        self.autostart_var = ctk.BooleanVar(value=False)
        self.autostart_switch = ctk.CTkSwitch(
            preferences, text="", variable=self.autostart_var, command=self._toggle_autostart,
            progress_color=ACCENT, button_color=TEXT, button_hover_color="#FFFFFF", width=44,
        )
        self.autostart_switch.grid(row=0, column=1, rowspan=2, padx=(16, 22), pady=15)
        if not self._autostart.supported:
            self.autostart_switch.configure(state="disabled")
        else:
            try:
                self.autostart_var.set(self._autostart.is_enabled())
            except OSError:
                pass
        self.feedback = self._label(body, "Закрытие окна сворачивает панель. Бот продолжит работать.", 12, MUTED, anchor="w")
        self.feedback.grid(row=6, column=0, sticky="ew", pady=(13, 0))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=30, pady=(12, 18))
        self.last_check = self._label(footer, "Обновление каждые 10 секунд", 11, MUTED)
        self.last_check.pack(side="left")
        ctk.CTkButton(footer, text="Обновить", command=self.refresh, width=82, height=28,
                      fg_color="transparent", hover_color=CARD, text_color=MUTED).pack(side="right")
        ctk.CTkButton(footer, text="Выйти из панели", command=self._quit, width=120, height=28,
                      fg_color="transparent", hover_color=CARD, text_color=MUTED).pack(side="right", padx=8)

    def _sync_profile_cards(self):
        if set(self._profile_cards) != {p.id for p in self.profiles}:
            for widgets in self._profile_cards.values():
                widgets["frame"].destroy()
            self._profile_cards = {}
            for index, profile in enumerate(self.profiles):
                frame = ctk.CTkFrame(self.dashboard, fg_color=CARD, corner_radius=18,
                                     border_width=1, border_color=BORDER, cursor="hand2")
                frame.grid(row=index * 2, column=0, sticky="ew", pady=(0, 12))
                frame.grid_columnconfigure(1, weight=1)
                image_label = self._label(frame, "", 30, ACCENT, bold=True, width=64, height=64)
                image_label.grid(row=0, column=0, rowspan=3, padx=(18, 16), pady=14)
                name = self._label(frame, profile.name, 24, bold=True, anchor="w")
                name.grid(row=0, column=1, sticky="ew", pady=(14, 2))
                status = self._label(frame, "● Проверяем состояние", 13, MUTED, anchor="w")
                status.grid(row=1, column=1, sticky="ew")
                meta = self._label(frame, "", 11, MUTED, anchor="w")
                meta.grid(row=2, column=1, sticky="ew", pady=(3, 14))
                arrow = self._label(frame, "⌄", 24, MUTED, width=35)
                arrow.grid(row=0, column=2, rowspan=3, padx=(10, 20))
                widgets = dict(frame=frame, name=name, status=status, meta=meta, arrow=arrow, image_label=image_label)
                self._profile_cards[profile.id] = widgets
                for widget in (frame, name, status, meta, arrow, image_label):
                    widget.bind("<Button-1>", lambda event, key=profile.id: self._toggle_card(key), add="+")
        for profile in self.profiles:
            widgets = self._profile_cards[profile.id]
            widgets["name"].configure(text=profile.name)
            state = self._profile_statuses.get(profile.id)
            text, color = {"running": ("Работает", GREEN), "starting": ("Запускается", AMBER),
                           "offline": ("Нет связи с сервисами", AMBER), "stopped": ("Остановлен", MUTED)}.get(state, ("Проверяем состояние", MUTED))
            widgets["status"].configure(text="● " + text, text_color=color)
            info = self._dashboard_statuses.get(profile.id)
            uptime = " · В работе " + format_uptime(info.uptime_seconds) if info and info.pid else ""
            widgets["meta"].configure(text=f"{profile.currency} · {profile.timezone}{uptime}")
            expanded = self._expanded_profile == profile.id
            widgets["arrow"].configure(text="⌃" if expanded else "⌄")
            widgets["frame"].configure(border_color=ACCENT if expanded else BORDER)
            source = load_profile_image(profile, BASE_DIR, size=(64, 64))
            if source is not None:
                try:
                    widgets["image"] = ctk.CTkImage(light_image=source.copy(), dark_image=source.copy(), size=(64, 64))
                finally:
                    source.close()
                widgets["image_label"].configure(image=widgets["image"], text="")
            else:
                widgets["image_label"].configure(image=None, text=profile.name[:1].upper())
        running = sum(state == "running" for state in self._profile_statuses.values())
        self.dashboard_summary.configure(text=f"Ботов: {len(self.profiles)}   ·   Работают: {running}")

    def _toggle_card(self, profile_id):
        if getattr(self, "_saving_profile", False) or self._busy or self._picture_busy:
            self.feedback.configure(text="Дождитесь завершения текущей операции.", text_color=AMBER)
            return
        if self._expanded_profile == profile_id:
            self._expanded_profile = None
            self.detail_panel.grid_remove()
        else:
            profile = next(p for p in self.profiles if p.id == profile_id)
            self._select_profile(self._profile_label(profile))
            self._expanded_profile = profile_id
            index = next(i for i, p in enumerate(self.profiles) if p.id == profile_id)
            self.detail_panel.grid(row=index * 2 + 1, column=0, sticky="ew", padx=12, pady=(0, 22))
            status = self._dashboard_statuses.get(profile_id)
            if status:
                self._render_status(status)
        self.picture_controls.grid_remove()
        self._sync_profile_cards()
        if self._expanded_profile:
            self.after_idle(self._reveal_expanded_card)

    def _reveal_expanded_card(self):
        if self._closed or not self._expanded_profile:
            return
        canvas = self._dashboard_scroll._parent_canvas
        frame = self._profile_cards[self._expanded_profile]["frame"]
        bounds = canvas.bbox("all")
        if bounds:
            target = canvas.canvasy(0) + frame.winfo_rooty() - canvas.winfo_rooty() - 8
            canvas.yview_moveto(max(0, target) / max(1, bounds[3]))

    def _render_dashboard(self, statuses):
        self._dashboard_statuses = statuses
        self._profile_statuses = {key: value.state for key, value in statuses.items()}
        self._sync_profile_cards()
        selected = statuses.get(self.selected_profile.id)
        if selected:
            self._render_status(selected)

    def _show_picture_controls(self, event=None):
        if self._picture_hide_id is not None:
            self.after_cancel(self._picture_hide_id)
            self._picture_hide_id = None
        self.picture_controls.grid(row=1, column=0, padx=6, pady=6)

    def _schedule_picture_hide(self, event=None):
        if self._picture_hide_id is not None:
            self.after_cancel(self._picture_hide_id)
        self._picture_hide_id = self.after(100, self._hide_picture_controls)

    def _hide_picture_controls(self):
        self._picture_hide_id = None
        x, y = self.winfo_pointerxy()
        inside = (self.logo_card.winfo_rootx() <= x < self.logo_card.winfo_rootx() + self.logo_card.winfo_width()
                  and self.logo_card.winfo_rooty() <= y < self.logo_card.winfo_rooty() + self.logo_card.winfo_height())
        if not inside:
            self.picture_controls.grid_remove()

    def _set_icon(self):
        try:
            source = load_profile_image(self.selected_profile, BASE_DIR, size=(64, 64))
            if source is None:
                source = Image.new("RGBA", (64, 64), (17, 19, 25, 255))
            try:
                self._window_icon = ImageTk.PhotoImage(source)
            finally:
                source.close()
            self.iconphoto(True, self._window_icon)
        except (OSError, RuntimeError):
            pass

    def _render_profile_image(self):
        source = load_profile_image(self.selected_profile, BASE_DIR)
        initial = "" if source is not None else (self.selected_profile.name.strip()[:1].upper() or "B")
        if source is None:
            source = Image.new("RGBA", (146, 146), (0, 0, 0, 0))
        try:
            self.logo_image = ctk.CTkImage(light_image=source.copy(), dark_image=source.copy(), size=(146, 146))
        finally:
            source.close()
        self.logo_label.configure(image=self.logo_image, text=initial)

    def _picture_change_allowed(self):
        if self._picture_busy or getattr(self, "_saving_profile", False):
            self.feedback.configure(text="Дождитесь завершения сохранения.", text_color=AMBER)
            return False
        if self._editor is not None and self._editor.winfo_exists():
            self.feedback.configure(text="Закройте настройки перед изменением картинки.", text_color=AMBER)
            return False
        return not self._closed

    def _choose_profile_picture(self):
        if not self._picture_change_allowed():
            return
        profile_id = self.selected_profile.id
        path = filedialog.askopenfilename(parent=self, title="Картинка выбранного бота",
                                         filetypes=[("Изображения", "*.png *.jpg *.jpeg *.webp *.bmp")])
        if path:
            self._save_picture(path, profile_id=profile_id)

    def _clear_profile_picture(self):
        if self._picture_change_allowed():
            self._save_picture(None)

    def _save_picture(self, path, *, profile_id=None):
        self._picture_busy = True
        self.picture_button.configure(state="disabled")
        self.picture_reset_button.configure(state="disabled")
        self.feedback.configure(text="Сохраняем картинку…", text_color=MUTED)
        self._submit("picture", save_profile_picture, profile_id or self.selected_profile.id, path)

    def _finish_picture_save(self, profile, error):
        self._picture_busy = False
        self.picture_button.configure(state="normal")
        self.picture_reset_button.configure(state="normal")
        if error or profile is None:
            self.feedback.configure(text="Не удалось сохранить картинку. Выберите PNG, JPEG, WebP или BMP до 10 МБ.", text_color=RED)
            return
        self.profiles = list_profiles(BASE_DIR)
        self._sync_profile_cards()
        if profile.id == self.selected_profile.id:
            self.selected_profile = next(p for p in self.profiles if p.id == profile.id)
            self._render_profile_image()
            self._set_icon()
        self.feedback.configure(text=f"Картинка бота «{profile.name}» сохранена.", text_color=GREEN)

    def _submit(self, kind, function, *args):
        def work():
            try:
                self._events.put((kind, function(*args), None))
            except Exception as exc:
                logging.error("Desktop operation failed: %s", kind)
                self._events.put((kind, None, exc))
        self._executor.submit(work)

    def refresh(self):
        if self._refresh_pending or self._closed:
            return
        self._refresh_pending = True
        self._submit(("dashboard", self._generation), collect_dashboard_statuses, tuple(self.profiles))

    def _scheduled_refresh(self):
        self.refresh()
        if not self._closed:
            self._refresh_id = self.after(REFRESH_SECONDS * 1000, self._scheduled_refresh)

    def _drain_events(self):
        while not self._closed:
            try:
                kind, result, error = self._events.get_nowait()
            except Empty:
                break
            if isinstance(kind, tuple):
                kind, generation = kind
                if generation != self._generation:
                    continue
            if kind == "picture":
                self._finish_picture_save(result, error)
                continue
            if kind == "profile-save":
                self._finish_profile_save(result, error)
                continue
            if kind == "dashboard":
                self._refresh_pending = False
                if error:
                    self.last_check.configure(text="Не удалось обновить состояния. Повторим проверку.", text_color=AMBER)
                else:
                    self._render_dashboard(result)
                if self._refresh_again:
                    self._refresh_again = False
                    self.refresh()
                continue
            if kind == "status":
                self._refresh_pending = False
                if error:
                    self.last_check.configure(text="Проверка не удалась. Попробуем снова.", text_color=AMBER)
                else:
                    self._render_status(result)
                if self._refresh_again:
                    self._refresh_again = False
                    self.refresh()
            elif kind == "action":
                self._busy = False
                self.feedback.configure(
                    text="Команда не выполнена. Откройте лог для подробностей." if error else "Команда выполнена. Обновляем состояние…",
                    text_color=RED if error else MUTED,
                )
                self._update_buttons()
                if self._refresh_pending:
                    self._refresh_again = True
                else:
                    self.refresh()
        if self._closed:
            return
        try:
            if SHOW_REQUEST_FILE.exists():
                request = SHOW_REQUEST_FILE.read_text(encoding="utf-8").strip()
                SHOW_REQUEST_FILE.unlink(missing_ok=True)
                if request in {"start", "show-and-start"}:
                    self._startup_requested = True
                if request in {"show", "show-and-start"}:
                    self.show_panel()
                else:
                    self.refresh()
        except OSError:
            pass
        self._poll_id = self.after(150, self._drain_events)

    def _render_status(self, status: DesktopStatus):
        self._last_status = status
        self._profile_statuses[self.selected_profile.id] = status.state
        self.profile_menu.configure(values=self._profile_labels())
        self.profile_menu.set(self._profile_label(self.selected_profile))
        self._sync_profile_cards()
        self._keep_accessible()
        title, detail, color, badge = {
            "running": ("Бот работает", "Готов принимать ваши траты в Telegram.", GREEN, "На связи"),
            "offline": ("Нужна связь с сетью", "Бот запущен, но один из сервисов недоступен.", AMBER, "Проверьте соединение"),
            "starting": ("Бот запускается", "Подключаем Telegram и готовим бота к работе.", AMBER, "Запуск"),
            "stopped": ("Бот остановлен", "Нажмите «Запустить», чтобы вернуться на связь.", MUTED, "Не запущен"),
        }[status.state]
        self.badge.configure(text=f"●  {badge}", text_color=color)
        self.headline.configure(text=title)
        self.description.configure(text=detail)
        self.version_label.configure(text=f"Бот  {status.version}")
        self.uptime_label.configure(text="В работе  " + format_uptime(status.uptime_seconds if status.pid else None))
        for name in ("telegram", "google"):
            connection = getattr(status, name)
            text = f"●  Доступен  ·  {connection.latency_ms} мс" if connection.reachable else "●  Нет соединения"
            self.connection_widgets[name].configure(text=text, text_color=GREEN if connection.reachable else AMBER)
        self.last_check.configure(text=f"Проверено в {status.checked_at:%H:%M:%S}  ·  Автообновление 10 с", text_color=MUTED)
        self._update_buttons()
        if self._startup_requested and not self._busy:
            if status.pid:
                self._startup_requested = False
            elif status.telegram.reachable and status.google.reachable:
                self._action("start")
            else:
                self.feedback.configure(text="Ждём подключения к Telegram и Google для запуска бота.", text_color=AMBER)

    def _update_buttons(self):
        running = bool(self._last_status and self._last_status.pid)
        self.edit_button.configure(state="disabled" if self._busy or getattr(self, "_saving_profile", False) else "normal")
        for command, button in self.action_buttons.items():
            enabled = not self._busy and not getattr(self, "_saving_profile", False) and ((command == "start" and not running) or (command != "start" and running))
            button.configure(state="normal" if enabled else "disabled")

    def _action(self, command):
        if self._busy or self._closed:
            return
        self._busy = True
        self._startup_requested = False
        self._update_buttons()
        self.feedback.configure(text={"start": "Запускаем бота…", "restart": "Перезапускаем бота…", "stop": "Останавливаем бота…"}[command], text_color=MUTED)
        self._submit(("action", self._generation), run_manager_action, command, self.selected_profile.id)

    def _toggle_autostart(self):
        enabled = self.autostart_var.get()
        try:
            self._autostart.set_enabled(enabled)
        except OSError:
            self.autostart_var.set(not enabled)
            self.feedback.configure(text="Не удалось изменить автозапуск Windows.", text_color=RED)
        else:
            self.feedback.configure(text="Автозапуск при входе в Windows включён." if enabled else "Автозапуск Windows выключен.", text_color=MUTED)

    def _open_log(self):
        path = self.selected_profile.runtime_dir(BASE_DIR) / "bot.log"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(exist_ok=True)
            if os.name == "nt":
                os.startfile(path)
            else:
                webbrowser.open(path.as_uri())
        except OSError:
            self.feedback.configure(text="Не удалось открыть лог.", text_color=RED)

    def _profile_label(self, profile):
        state = self._profile_statuses.get(profile.id)
        badge = {"running": "работает", "stopped": "остановлен", "offline": "нет сети", "starting": "запускается"}.get(state, "не проверен")
        return f"{profile.name} ({profile.id}) — {badge}"

    def _profile_labels(self):
        return [self._profile_label(profile) for profile in self.profiles]

    def _select_profile(self, label):
        profile = next((p for p in self.profiles if self._profile_label(p) == label), None)
        if profile is None or profile.id == self.selected_profile.id:
            return
        self._generation += 1
        self.selected_profile = profile
        self.profile_menu.set(self._profile_label(profile))
        self._render_profile_image()
        self._set_icon()
        self._last_status = None
        self._refresh_pending = self._busy = self._refresh_again = self._startup_requested = False
        self.profile_autostart_var.set(profile.autostart)
        self.headline.configure(text=profile.name)
        self.badge.configure(text="Проверяем выбранного бота", text_color=MUTED)
        self._update_buttons()
        # Until status is known, avoid submitting a start to an already running profile.
        for button in self.action_buttons.values():
            button.configure(state="disabled")
        if self._expanded_profile is not None:
            self._expanded_profile = profile.id
            index = next(i for i, item in enumerate(self.profiles) if item.id == profile.id)
            self.detail_panel.grid(row=index * 2 + 1, column=0, sticky="ew", padx=12, pady=(0, 22))
            self._sync_profile_cards()
        self.refresh()

    def _toggle_profile_autostart(self):
        if self._picture_busy:
            self.profile_autostart_var.set(self.selected_profile.autostart)
            self.feedback.configure(text="Дождитесь сохранения картинки.", text_color=AMBER)
            return
        enabled = self.profile_autostart_var.get()
        try:
            profile = update_profile(replace(self.selected_profile, autostart=enabled), base_dir=BASE_DIR)
        except Exception:
            self.profile_autostart_var.set(not enabled)
            self.feedback.configure(text="Не удалось сохранить автозапуск профиля.", text_color=RED)
            return
        self.selected_profile = profile
        self.profiles = list_profiles(BASE_DIR)
        self.feedback.configure(text="Выбор сохранён. Для входа в Windows включите общий автозапуск выше.", text_color=MUTED)

    def _open_spreadsheet(self):
        spreadsheet_id = self.selected_profile.spreadsheet_id
        if self.selected_profile.legacy and not spreadsheet_id:
            from config import SPREADSHEET_ID
            spreadsheet_id = SPREADSHEET_ID
        if spreadsheet_id:
            webbrowser.open(f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit")

    def _add_profile(self):
        self._show_profile_editor(None)

    def _edit_profile(self):
        if self._busy or getattr(self, "_saving_profile", False):
            self.feedback.configure(text="Дождитесь завершения текущей операции.", text_color=AMBER)
            return
        self._show_profile_editor(self.selected_profile)

    def _show_profile_editor(self, profile):
        if self._picture_busy:
            self.feedback.configure(text="Дождитесь сохранения картинки.", text_color=AMBER)
            return
        if getattr(self, "_saving_profile", False):
            self.feedback.configure(text="Дождитесь окончания текущей проверки профиля.", text_color=AMBER)
            return
        if self._editor is not None and self._editor.winfo_exists():
            self._editor.lift()
            return
        editor = self._editor = ctk.CTkToplevel(self, fg_color=BG)
        editor_generation = self._generation
        cancelled = Event()
        def cancel_editor():
            cancelled.set()
            editor.destroy()
        editor.protocol("WM_DELETE_WINDOW", cancel_editor)
        editor.title("Настройки бота" if profile else "Добавить бота")
        editor.geometry("560x640")
        editor.transient(self)
        editor.grid_columnconfigure(0, weight=1)
        editor.grid_rowconfigure(0, weight=1)
        form = ctk.CTkScrollableFrame(editor, fg_color=BG)
        form.grid(row=0, column=0, sticky="nsew", padx=18, pady=18)
        form.grid_columnconfigure(0, weight=1)
        fields = {}
        editable = editable_profile(profile)
        definitions = [("name", "Название"), ("id", "ID профиля (строчная латиница, цифры, - и _)"),
                       ("spreadsheet_id", "Ссылка или ID Google Sheets"), ("currency", "Валюта"),
                       ("timezone", "Часовой пояс"), ("credentials_file", "Путь к ключу Google (пусто — общий ключ)"),
                       ("token", "Токен Telegram (пусто — сохранить текущий)" if profile else "Токен Telegram из BotFather")]
        for row, (key, label) in enumerate(definitions):
            self._label(form, label, 13).grid(row=row * 2, column=0, sticky="w", pady=(10, 4))
            if key == "currency":
                widget = ctk.CTkOptionMenu(form, values=["EUR", "RUB"])
                widget.set(profile.currency if profile else "EUR")
            else:
                widget = ctk.CTkEntry(form, height=36, show="•" if key == "token" else "")
                value = getattr(editable, key, "") if profile else ("Europe/Moscow" if key == "timezone" else "")
                widget.insert(0, value)
                if profile and key == "id":
                    widget.configure(state="disabled")
                install_entry_editing(widget)
            widget.grid(row=row * 2 + 1, column=0, sticky="ew")
            fields[key] = widget
        source_tracking = ctk.BooleanVar(value=profile.track_money_source if profile else False)
        self._editor_source_tracking = source_tracking
        ctk.CTkCheckBox(
            form, text="Учитывать источник денег", variable=source_tracking,
            font=ctk.CTkFont(family=UI_FONT, size=13),
        ).grid(row=14, column=0, sticky="w", pady=(16, 4))
        notice = self._label(form, "Перед сохранением проверим подключение. При изменении рабочих параметров запущенный бот автоматически перезапустится.", 12, MUTED, wraplength=440)
        notice.grid(row=15, column=0, sticky="ew", pady=14)
        save = ctk.CTkButton(editor, text="Проверить и сохранить", height=38)
        save.grid(row=1, column=0, sticky="ew", padx=26, pady=(0, 8))
        cancel = ctk.CTkButton(editor, text="Отмена", fg_color=CARD, command=cancel_editor)
        cancel.grid(row=2, column=0, sticky="ew", padx=26, pady=(0, 18))
        editor.bind("<Escape>", lambda event: cancel_editor())

        def submit():
            try:
                values = {key: widget.get().strip() for key, widget in fields.items()}
                values["spreadsheet_id"] = normalize_spreadsheet_id(values["spreadsheet_id"])
                token = values.pop("token")
                values["track_money_source"] = bool(source_tracking.get())
                candidate = replace(editable, **values) if profile else BotProfile(**values)
            except Exception:
                notice.configure(text="Проверьте поля: название, ID профиля и ссылка на таблицу обязательны.", text_color=RED)
                return
            save.configure(state="disabled")
            self._saving_profile = True
            self._update_buttons()
            notice.configure(text="Проверяем Telegram и Google Sheets…", text_color=MUTED)
            # Form identity is separate from selected profile generation: switching
            # profiles cannot redirect this save or apply its response to another form.
            self._save_context = (editor, save, notice, candidate, editor_generation)
            self._submit("profile-save", save_validated_profile, candidate, profile, token, cancelled)
        save.configure(command=submit)

    def _finish_profile_save(self, result, error):
        self._saving_profile = False
        if hasattr(self, "_update_buttons"):
            self._update_buttons()
        editor, save, notice, candidate, generation = self._save_context
        if result and result[1]:
            self.profiles = list_profiles(BASE_DIR)
            self.profile_menu.configure(values=self._profile_labels())
        if not editor.winfo_exists():
            return
        save.configure(state="normal")
        if error or not result or not result[0].ok:
            notice.configure(text="Не удалось сохранить. Проверьте ID, валюту, часовой пояс и доступ к ключу." if error else result[0].message, text_color=RED)
            return
        if generation != self._generation:
            self.profile_menu.set(self._profile_label(self.selected_profile))
        elif self.selected_profile.id == result[1].id:
            self.selected_profile = result[1]
            self._generation += 1
            self._last_status = None
            self._refresh_pending = False
            self.profile_menu.set(self._profile_label(self.selected_profile))
            self.refresh()
        else:
            self._select_profile(self._profile_label(result[1]))
        if hasattr(self, "_sync_profile_cards"):
            self._sync_profile_cards()
        self.feedback.configure(text=result[0].message, text_color=GREEN)
        editor.destroy()

    def _tray_available(self):
        pid = read_int(BASE_DIR / ".tray.pid")
        return bool(pid and is_process_running(pid))

    def _hide(self):
        if self._tray_available():
            self.withdraw()
        else:
            self.iconify()

    def _keep_accessible(self):
        if self.state() == "withdrawn" and not self._tray_available():
            self.deiconify()
            self.iconify()

    def show_panel(self):
        self.deiconify()
        self.lift()
        self.focus_force()
        self.refresh()

    def _quit(self):
        self._closed = True
        self.after_cancel(self._poll_id)
        self.after_cancel(self._refresh_id)
        self._executor.shutdown(wait=False, cancel_futures=True)
        self.destroy()


def main() -> int:
    parser = argparse.ArgumentParser(description="Bot Budget desktop panel")
    parser.add_argument("--minimized", action="store_true")
    parser.add_argument("--start-bot", action="store_true")
    args = parser.parse_args()
    lock = ProcessLock(BASE_DIR / ".desktop.lock")
    if not lock.acquire():
        if args.start_bot or not args.minimized:
            request = "start" if args.minimized else "show-and-start" if args.start_bot else "show"
            SHOW_REQUEST_FILE.write_text(request, encoding="utf-8")
        return 0
    try:
        DESKTOP_PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
        logging.basicConfig(filename=BASE_DIR / "bot.log", level=logging.INFO,
                            format="%(asctime)s | %(levelname)s | desktop | %(message)s", encoding="utf-8")
        panel = BudgetPanel(minimized=args.minimized, start_bot=args.start_bot)
        panel.mainloop()
    finally:
        if read_int(DESKTOP_PID_FILE) == os.getpid():
            DESKTOP_PID_FILE.unlink(missing_ok=True)
        lock.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
