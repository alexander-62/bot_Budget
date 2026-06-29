import argparse
import os
import signal
import socket
import subprocess
import sys
import re
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from config import WEBAPP_HOST, WEBAPP_PORT, WEBAPP_URL


BASE_DIR = Path(__file__).resolve().parent
PID_FILE = BASE_DIR / ".bot.pid"
PORT_FILE = BASE_DIR / ".bot.port"
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


def _read_port() -> int | None:
    if not PORT_FILE.exists():
        return None
    try:
        return int(PORT_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def _write_port(port: int) -> None:
    PORT_FILE.write_text(str(port), encoding="utf-8")


def _clear_pid() -> None:
    if PID_FILE.exists():
        PID_FILE.unlink()


def _clear_port() -> None:
    if PORT_FILE.exists():
        PORT_FILE.unlink()


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


def _is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        try:
            sock.bind((WEBAPP_HOST, port))
        except OSError:
            return False
        return True


def _select_webapp_port(start_port: int) -> int:
    for port in range(start_port, 65536):
        if _is_port_free(port):
            return port
    raise RuntimeError(f"No free port found at or above {start_port}.")


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


def _build_runtime_webapp_url(port: int) -> str:
    parsed = urlparse(WEBAPP_URL)
    if not WEBAPP_URL or "example.com" in WEBAPP_URL:
        return f"http://{WEBAPP_HOST}:{port}/webapp"
    if parsed.scheme and parsed.netloc and parsed.hostname in {"127.0.0.1", "localhost", WEBAPP_HOST}:
        return urlunparse(parsed._replace(netloc=f"{parsed.hostname}:{port}"))

    return WEBAPP_URL


def _build_runtime_env(port: int) -> dict[str, str]:
    env = os.environ.copy()
    env["BOT_BUDGET_WEBAPP_HOST"] = WEBAPP_HOST
    env["BOT_BUDGET_WEBAPP_PORT"] = str(port)
    env["BOT_BUDGET_WEBAPP_URL"] = _build_runtime_webapp_url(port)
    return env


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

    runtime_port = WEBAPP_PORT
    if _is_webapp_port_busy():
        try:
            runtime_port = _select_webapp_port(WEBAPP_PORT + 1)
        except RuntimeError as exc:
            print(str(exc))
            return
        print(
            f"{_format_port_busy_message()} Switching Web App to next free port {runtime_port}."
        )

    if background:
        with LOG_FILE.open("a", encoding="utf-8") as log_file:
            kwargs = {
                "stdout": log_file,
                "stderr": log_file,
                "cwd": str(BASE_DIR),
                "env": _build_runtime_env(runtime_port),
            }
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            process = subprocess.Popen([sys.executable, "bot.py"], **kwargs)
        _write_pid(process.pid)
        _write_port(runtime_port)
        print(f"Bot started in background (PID {process.pid}). Log: {LOG_FILE.name}")
        return

    print("Starting in foreground. Stop with Ctrl+C")
    subprocess.run(
        [sys.executable, "bot.py"],
        cwd=str(BASE_DIR),
        check=False,
        env=_build_runtime_env(runtime_port),
    )


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
        _clear_port()


def status_bot() -> None:
    pid = _read_pid()
    runtime_port = _read_port() or WEBAPP_PORT
    if not pid:
        if _is_port_free(runtime_port):
            print("Bot is not running in background (no PID file).")
        else:
            print(
                f"Bot PID file missing, but Web App port {WEBAPP_HOST}:{runtime_port} is busy."
            )
        return

    if _is_running(pid):
        print(f"Bot is running in background (PID {pid}, Web App port {runtime_port}).")
    else:
        if not _is_port_free(runtime_port):
            print(
                f"PID file exists, bot process is not active, but "
                f"Web App port {WEBAPP_HOST}:{runtime_port} is busy."
            )
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
