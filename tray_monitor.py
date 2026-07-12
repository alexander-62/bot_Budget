from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from config import WEBAPP_HOST, WEBAPP_PORT, WEBAPP_URL
from version import __version__

try:
    import pystray
    from PIL import Image, ImageDraw, ImageFont
except Exception as exc:  # Tray must fail clearly without taking the bot down.
    pystray = None
    Image = None
    ImageDraw = None
    ImageFont = None
    TRAY_IMPORT_ERROR = exc
else:
    TRAY_IMPORT_ERROR = None


BASE_DIR = Path(__file__).resolve().parent
PID_FILE = BASE_DIR / ".bot.pid"
PORT_FILE = BASE_DIR / ".bot.port"
TRAY_PID_FILE = BASE_DIR / ".tray.pid"
LOG_FILE = BASE_DIR / "bot.log"
UPDATE_INTERVAL_SECONDS = 5


def _read_int(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def _write_tray_pid() -> None:
    TRAY_PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def _clear_tray_pid() -> None:
    if TRAY_PID_FILE.exists() and _read_int(TRAY_PID_FILE) == os.getpid():
        TRAY_PID_FILE.unlink()


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_bot_pid() -> int | None:
    return _read_int(PID_FILE)


def _read_runtime_port() -> int:
    return _read_int(PORT_FILE) or WEBAPP_PORT


def _build_runtime_webapp_url(port: int) -> str:
    parsed = urlparse(WEBAPP_URL)
    if not WEBAPP_URL or "example.com" in WEBAPP_URL:
        return f"http://{WEBAPP_HOST}:{port}/webapp"
    if parsed.scheme and parsed.netloc and parsed.hostname in {"127.0.0.1", "localhost", WEBAPP_HOST}:
        return urlunparse(parsed._replace(netloc=f"{parsed.hostname}:{port}"))
    return WEBAPP_URL


def _is_health_ok(port: int) -> bool:
    url = f"http://{WEBAPP_HOST}:{port}/webapp/health"
    try:
        with urllib.request.urlopen(url, timeout=1.0) as response:
            return response.status == 200
    except Exception:
        return False


def _is_port_busy(port: int) -> bool:
    try:
        with socket.create_connection((WEBAPP_HOST, port), timeout=0.3):
            return True
    except OSError:
        return False


def get_bot_status() -> tuple[str, str]:
    pid = _read_bot_pid()
    port = _read_runtime_port()
    health_ok = _is_health_ok(port)

    if pid and _is_running(pid) and health_ok:
        return "running", f"Бот работает\nPID: {pid}\nWeb App: {WEBAPP_HOST}:{port}\nВерсия: {__version__}"
    if pid and _is_running(pid):
        return "starting", f"Процесс бота запущен, health check пока недоступен\nPID: {pid}\nWeb App: {WEBAPP_HOST}:{port}"
    if _is_port_busy(port):
        return "warning", f"PID бота не найден, но порт Web App занят\nWeb App: {WEBAPP_HOST}:{port}"
    return "stopped", "Бот не запущен"


def _load_font(size: int):
    if ImageFont is None:
        return None
    for font_name in ("arial.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(font_name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def create_tray_image(status: str):
    if Image is None or ImageDraw is None:
        return None

    colors = {
        "running": (34, 139, 72),
        "starting": (210, 145, 32),
        "warning": (210, 145, 32),
        "stopped": (160, 45, 45),
    }
    bg = colors.get(status, colors["stopped"])
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((4, 4, 60, 60), radius=12, fill=bg)

    label = "B"
    font = _load_font(38)
    bbox = draw.textbbox((0, 0), label, font=font)
    x = (64 - (bbox[2] - bbox[0])) // 2
    y = (64 - (bbox[3] - bbox[1])) // 2 - 2
    draw.text((x, y), label, font=font, fill=(255, 255, 255))

    if status == "running":
        draw.ellipse((43, 43, 57, 57), fill=(160, 255, 190), outline=(255, 255, 255), width=2)
    elif status in {"starting", "warning"}:
        draw.rectangle((46, 42, 52, 50), fill=(255, 255, 255))
        draw.rectangle((46, 53, 52, 57), fill=(255, 255, 255))
    else:
        draw.line((44, 44, 56, 56), fill=(255, 255, 255), width=4)
        draw.line((56, 44, 44, 56), fill=(255, 255, 255), width=4)
    return image


def _run_manager(command: str) -> None:
    subprocess.Popen(
        [sys.executable, "manage_bot.py", command],
        cwd=str(BASE_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


class BotTray:
    def __init__(self) -> None:
        self.icon = None
        self.stop_event = threading.Event()
        self.last_status = "stopped"
        self.last_tooltip = "Бот не запущен"

    def run(self) -> int:
        if pystray is None or Image is None:
            print(f"Tray icon unavailable: {TRAY_IMPORT_ERROR}", file=sys.stderr)
            return 1

        existing_pid = _read_int(TRAY_PID_FILE)
        if existing_pid and existing_pid != os.getpid() and _is_running(existing_pid):
            return 0

        _write_tray_pid()
        self.last_status, self.last_tooltip = get_bot_status()
        self.icon = pystray.Icon(
            "BotBudget",
            create_tray_image(self.last_status),
            self.last_tooltip,
            self._build_menu(),
        )
        updater = threading.Thread(target=self._update_loop, name="BotBudgetTrayUpdater", daemon=True)
        updater.start()
        try:
            self.icon.run()
        finally:
            self.stop_event.set()
            _clear_tray_pid()
        return 0

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem("Статус", self._show_status, default=True),
            pystray.MenuItem("Открыть Web App", self._open_webapp),
            pystray.MenuItem("Открыть лог", self._open_log),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Перезапустить бота", self._restart_bot),
            pystray.MenuItem("Остановить бота", self._stop_bot),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Закрыть иконку", self._exit_tray),
        )

    def _update_loop(self) -> None:
        while not self.stop_event.wait(UPDATE_INTERVAL_SECONDS):
            self.update_icon()

    def update_icon(self) -> None:
        if self.icon is None:
            return
        status, tooltip = get_bot_status()
        if status == self.last_status and tooltip == self.last_tooltip:
            return
        self.last_status = status
        self.last_tooltip = tooltip
        self.icon.icon = create_tray_image(status)
        self.icon.title = tooltip

    def _show_status(self, _icon=None, _item=None) -> None:
        self.update_icon()
        if self.icon is not None:
            self.icon.notify(self.last_tooltip, "Bot Budget")

    def _open_webapp(self, _icon=None, _item=None) -> None:
        webbrowser.open(_build_runtime_webapp_url(_read_runtime_port()))

    def _open_log(self, _icon=None, _item=None) -> None:
        if not LOG_FILE.exists():
            LOG_FILE.write_text("", encoding="utf-8")
        if os.name == "nt":
            os.startfile(LOG_FILE)  # type: ignore[attr-defined]
        else:
            webbrowser.open(LOG_FILE.as_uri())

    def _restart_bot(self, _icon=None, _item=None) -> None:
        _run_manager("restart")
        if self.icon is not None:
            self.icon.notify("Команда перезапуска отправлена", "Bot Budget")

    def _stop_bot(self, _icon=None, _item=None) -> None:
        _run_manager("stop")
        if self.icon is not None:
            self.icon.notify("Команда остановки отправлена", "Bot Budget")

    def _exit_tray(self, _icon=None, _item=None) -> None:
        self.stop_event.set()
        if self.icon is not None:
            self.icon.stop()


def main() -> int:
    try:
        return BotTray().run()
    except Exception as exc:
        timestamp = datetime.now().isoformat(timespec="seconds")
        with LOG_FILE.open("a", encoding="utf-8") as log_file:
            log_file.write(f"{timestamp} | ERROR | tray | {type(exc).__name__}: {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
