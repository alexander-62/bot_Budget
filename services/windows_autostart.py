"""Per-user Windows startup; no administrator access or global settings."""

import hashlib
from pathlib import Path
import subprocess
import sys


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


class WindowsAutostart:
    def __init__(self, base_dir: Path, executable: str | None = None):
        self.base_dir = base_dir.resolve()
        executable_path = Path(executable or sys.executable)
        pythonw = executable_path.with_name("pythonw.exe")
        self.executable = str(pythonw if pythonw.exists() else executable_path)
        identity = str(self.base_dir).casefold().encode("utf-8")
        self.value_name = "BotBudget-" + hashlib.sha256(identity).hexdigest()[:12]

    @property
    def supported(self) -> bool:
        return sys.platform == "win32"

    @property
    def command(self) -> str:
        return subprocess.list2cmdline([
            self.executable, str(self.base_dir / "manage_bot.py"),
            "ui", "--minimized", "--start-bot",
        ])

    def is_enabled(self) -> bool:
        if not self.supported:
            return False
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                value, _ = winreg.QueryValueEx(key, self.value_name)
                return value == self.command
        except FileNotFoundError:
            return False

    def set_enabled(self, enabled: bool) -> None:
        if not self.supported:
            raise OSError("Автозапуск доступен только в Windows.")
        import winreg

        if enabled:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.SetValueEx(key, self.value_name, 0, winreg.REG_SZ, self.command)
        else:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, self.value_name)
            except FileNotFoundError:
                pass
