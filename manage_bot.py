import argparse
import os
import signal
import socket
import subprocess
import sys
import re
from pathlib import Path

from config import WEBAPP_HOST, WEBAPP_PORT


BASE_DIR = Path(__file__).resolve().parent
PID_FILE = BASE_DIR / ".bot.pid"
LOG_FILE = BASE_DIR / "bot.log"


def _read_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def _write_pid(pid: int) -> None:
    PID_FILE.write_text(str(pid), encoding="utf-8")


def _clear_pid() -> None:
    if PID_FILE.exists():
        PID_FILE.unlink()


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _is_webapp_port_busy() -> bool:
    try:
        with socket.create_connection((WEBAPP_HOST, WEBAPP_PORT), timeout=0.3):
            return True
    except OSError:
        return False


def _find_webapp_port_owner_pid() -> int | None:
    if os.name != "nt":
        return None

    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
    except OSError:
        return None

    port_pattern = re.compile(rf"^\s*TCP\s+\S+:{WEBAPP_PORT}\s+\S+\s+LISTENING\s+(\d+)\s*$")
    for line in result.stdout.splitlines():
        match = port_pattern.match(line)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
    return None


def _describe_pid(pid: int) -> str | None:
    if os.name != "nt":
        return None

    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "LIST", "/NH"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
    except OSError:
        return None

    for line in result.stdout.splitlines():
        if line.startswith("Image Name:"):
            return line.split(":", 1)[1].strip()
    return None


def _format_port_busy_message() -> str:
    owner_pid = _find_webapp_port_owner_pid()
    if owner_pid is None:
        return f"Web App port {WEBAPP_HOST}:{WEBAPP_PORT} is already in use."

    owner_name = _describe_pid(owner_pid)
    if owner_name:
        return f"Web App port {WEBAPP_HOST}:{WEBAPP_PORT} is already in use by PID {owner_pid} ({owner_name})."

    return f"Web App port {WEBAPP_HOST}:{WEBAPP_PORT} is already in use by PID {owner_pid}."


def start_bot(background: bool = True) -> None:
    pid = _read_pid()
    if pid and _is_running(pid):
        print(f"Bot is already running (PID {pid}).")
        return

    if _is_webapp_port_busy():
        print(f"{_format_port_busy_message()} Stop old bot process or free port before start.")
        return

    if background:
        with LOG_FILE.open("a", encoding="utf-8") as log_file:
            kwargs = {
                "stdout": log_file,
                "stderr": log_file,
                "cwd": str(BASE_DIR),
            }
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            process = subprocess.Popen([sys.executable, "bot.py"], **kwargs)
        _write_pid(process.pid)
        print(f"Bot started in background (PID {process.pid}). Log: {LOG_FILE.name}")
        return

    print("Starting in foreground. Stop with Ctrl+C")
    subprocess.run([sys.executable, "bot.py"], cwd=str(BASE_DIR), check=False)


def stop_bot() -> None:
    pid = _read_pid()
    if not pid:
        print("PID file not found. Bot is probably not running in background.")
        return

    if not _is_running(pid):
        print("Process is not active. Cleaning PID file.")
        _clear_pid()
        return

    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            os.kill(pid, signal.SIGTERM)
        print(f"Bot stopped (PID {pid}).")
    finally:
        _clear_pid()


def status_bot() -> None:
    pid = _read_pid()
    if not pid:
        if _is_webapp_port_busy():
            print(f"Bot PID file missing, but {_format_port_busy_message().lower()}")
        else:
            print("Bot is not running in background (no PID file).")
        return

    if _is_running(pid):
        print(f"Bot is running in background (PID {pid}).")
    else:
        if _is_webapp_port_busy():
            print(f"PID file exists, bot process is not active, but {_format_port_busy_message().lower()}")
        else:
            print("PID file exists, but process is not active.")


def restart_bot() -> None:
    stop_bot()
    start_bot(background=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Telegram bot process manager")
    sub = parser.add_subparsers(dest="command", required=True)

    start_parser = sub.add_parser("start", help="Start bot")
    start_parser.add_argument(
        "--foreground",
        action="store_true",
        help="Run in current console (no background)",
    )

    sub.add_parser("stop", help="Stop background bot")
    sub.add_parser("restart", help="Restart background bot")
    sub.add_parser("status", help="Show bot status")

    args = parser.parse_args()

    if args.command == "start":
        start_bot(background=not args.foreground)
        return
    if args.command == "stop":
        stop_bot()
        return
    if args.command == "restart":
        restart_bot()
        return
    if args.command == "status":
        status_bot()
        return


if __name__ == "__main__":
    main()
