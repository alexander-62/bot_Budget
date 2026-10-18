"""Small Windows control panel; Telegram and Sheets stay in the bot process."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import logging
import os
from pathlib import Path
from queue import Empty, Queue
import subprocess
import sys
import webbrowser

from config import WEBAPP_HOST, WEBAPP_PORT
import customtkinter as ctk
from PIL import Image, ImageTk

from services.desktop_status import DesktopStatus, collect_status, format_uptime, read_int
from services.process_control import ProcessLock, is_process_running
from services.windows_autostart import WindowsAutostart
from version import __version__


BASE_DIR = Path(__file__).resolve().parent
DESKTOP_PID_FILE = BASE_DIR / ".desktop.pid"
SHOW_REQUEST_FILE = BASE_DIR / ".desktop.show"
REFRESH_SECONDS = 10
BG, CARD, BORDER = "#111319", "#1B1E27", "#2B303D"
TEXT, MUTED, ACCENT = "#F4F4F6", "#9A9FAF", "#F2B2BE"
GREEN, AMBER, RED = "#65D6A5", "#E9BF77", "#F08D95"
UI_FONT = "Segoe UI" if os.name == "nt" else "DejaVu Sans"


def run_manager_action(command: str) -> str:
    if command not in {"start", "stop", "restart"}:
        raise ValueError("Неизвестная команда управления.")
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(
        [sys.executable, str(BASE_DIR / "manage_bot.py"), command],
        cwd=BASE_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", timeout=30, check=False, **kwargs,
    )
    if result.returncode:
        raise RuntimeError("Команда не выполнена. Подробности — в bot.log.")
    return result.stdout.strip()


class BudgetPanel(ctk.CTk):
    def __init__(self, *, minimized: bool = False, start_bot: bool = False):
        ctk.set_appearance_mode("dark")
        if os.name != "nt":
            ctk.DrawEngine.preferred_drawing_method = "polygon_shapes"
        super().__init__(fg_color=BG)
        self.title("Bot Budget — панель управления")
        self.geometry("880x790")
        self.minsize(820, 740)
        self.protocol("WM_DELETE_WINDOW", self._hide)
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="BudgetPanel")
        self._events = Queue()
        self._closed = False
        self._refresh_pending = False
        self._busy = False
        self._startup_requested = start_bot
        self._refresh_again = False
        self._last_status = None
        self._autostart = WindowsAutostart(BASE_DIR)
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
            parent, text=text, text_color=color, height=0,
            font=ctk.CTkFont(family=UI_FONT, size=size, weight="bold" if bold else "normal"),
            **kwargs,
        )

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=30, pady=(26, 18))
        self._label(header, "Bot Budget", 27, bold=True).pack(side="left")
        self._label(header, "ПАНЕЛЬ УПРАВЛЕНИЯ", 11, MUTED).pack(side="left", padx=18, pady=(6, 0))
        self._label(header, "●  Локально", 12, MUTED).pack(side="right", pady=(6, 0))

        body = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0, scrollbar_button_color=BORDER)
        body.grid(row=1, column=0, sticky="nsew", padx=30)
        body.grid_columnconfigure(0, weight=1)

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
        logo_card = ctk.CTkFrame(hero, width=158, height=158, fg_color="#FFFFFF", corner_radius=20)
        logo_card.grid(row=0, column=1, rowspan=4, padx=(18, 24), pady=24)
        logo_card.grid_propagate(False)
        logo_card.grid_rowconfigure(0, weight=1)
        logo_card.grid_columnconfigure(0, weight=1)
        logo_path = BASE_DIR / "logo.png"
        try:
            with Image.open(logo_path) as source:
                self.logo_image = ctk.CTkImage(light_image=source.copy(), dark_image=source.copy(), size=(146, 146))
            ctk.CTkLabel(logo_card, text="", image=self.logo_image).grid(row=0, column=0)
        except OSError:
            self._label(logo_card, "B", 70, "#9A5868", bold=True).grid(row=0, column=0)

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
        self._label(preferences, "Запускать вместе с Windows", 14, bold=True).grid(
            row=0, column=0, sticky="w", padx=20, pady=(17, 0),
        )
        self._label(preferences, "Бот включится при входе, панель останется в трее.", 12, MUTED).grid(
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

    def _set_icon(self):
        try:
            with Image.open(BASE_DIR / "logo.png") as source:
                self._window_icon = ImageTk.PhotoImage(source.resize((64, 64)))
            self.iconphoto(True, self._window_icon)
        except (OSError, RuntimeError):
            pass

    def _submit(self, kind, function, *args):
        def work():
            try:
                self._events.put((kind, function(*args), None))
            except Exception as exc:
                logging.exception("Desktop operation failed: %s", kind)
                self._events.put((kind, None, exc))
        self._executor.submit(work)

    def refresh(self):
        if self._refresh_pending or self._closed:
            return
        self._refresh_pending = True
        self._submit("status", collect_status, BASE_DIR, WEBAPP_HOST, WEBAPP_PORT, __version__)

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
        for command, button in self.action_buttons.items():
            enabled = not self._busy and ((command == "start" and not running) or (command != "start" and running))
            button.configure(state="normal" if enabled else "disabled")

    def _action(self, command):
        if self._busy or self._closed:
            return
        self._busy = True
        self._startup_requested = False
        self._update_buttons()
        self.feedback.configure(text={"start": "Запускаем бота…", "restart": "Перезапускаем бота…", "stop": "Останавливаем бота…"}[command], text_color=MUTED)
        self._submit("action", run_manager_action, command)

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
        path = BASE_DIR / "bot.log"
        try:
            path.touch(exist_ok=True)
            if os.name == "nt":
                os.startfile(path)
            else:
                webbrowser.open(path.as_uri())
        except OSError:
            self.feedback.configure(text="Не удалось открыть лог.", text_color=RED)

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
