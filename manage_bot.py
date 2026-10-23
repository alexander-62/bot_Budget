import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import re
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse

# Management always reads shared operational settings from the personal config.
# Selected worker credentials are loaded only by the worker, after CLI selection.
_inherited_profile = os.environ.pop("BOT_BUDGET_PROFILE", None)
try:
    from config import WEBAPP_HOST, WEBAPP_PORT, WEBAPP_URL
finally:
    if _inherited_profile is not None:
        os.environ["BOT_BUDGET_PROFILE"] = _inherited_profile

# Direct manager invocations may inherit a profile with an ephemeral-port default.
WEBAPP_PORT = WEBAPP_PORT or 8080
from services.process_control import (
    AlreadyRunningError,
    ProcessLock,
    is_lock_held,
    process_birth_identity,
    recorded_process_identity,
    is_process_running as _is_running,
)


BASE_DIR = Path(__file__).resolve().parent
PID_FILE = BASE_DIR / ".bot.pid"
PORT_FILE = BASE_DIR / ".bot.port"
LOG_FILE = BASE_DIR / "bot.log"
TRAY_PID_FILE = BASE_DIR / ".tray.pid"
BOT_LOCK_FILE = BASE_DIR / ".bot.lock"
START_LOCK_FILE = BASE_DIR / ".bot-start.lock"
TRAY_LOCK_FILE = BASE_DIR / ".tray.lock"
TRAY_START_LOCK_FILE = BASE_DIR / ".tray-start.lock"
DESKTOP_LOCK_FILE = BASE_DIR / ".desktop.lock"
DESKTOP_START_LOCK_FILE = BASE_DIR / ".desktop-start.lock"
DESKTOP_PID_FILE = BASE_DIR / ".desktop.pid"
DESKTOP_SHOW_FILE = BASE_DIR / ".desktop.show"
PROFILE_ID = "personal"
EXIT_CODE = 0


def configure_profile(profile_id: str = "personal") -> None:
    """Select worker paths; shared panel/tray paths always remain global."""
    from services.bot_profiles import get_profile
    global PROFILE_ID, PID_FILE, PORT_FILE, LOG_FILE, BOT_LOCK_FILE, START_LOCK_FILE
    profile = get_profile(profile_id, base_dir=BASE_DIR)
    runtime_dir = profile.runtime_dir(BASE_DIR)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    PROFILE_ID = profile.id
    PID_FILE = runtime_dir / ".bot.pid"
    PORT_FILE = runtime_dir / ".bot.port"
    LOG_FILE = runtime_dir / "bot.log"
    BOT_LOCK_FILE = runtime_dir / ".bot.lock"
    START_LOCK_FILE = runtime_dir / ".bot-start.lock"


def _shared_runtime_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("BOT_BUDGET_PROFILE", None)
    return env


def start_autostart() -> None:
    from services.bot_profiles import list_profiles
    start_desktop(minimized=True)
    for profile in list_profiles(base_dir=BASE_DIR):
        if profile.autostart:
            configure_profile(profile.id)
            start_bot()



def _failure(message: str) -> None:
    global EXIT_CODE
    EXIT_CODE = 1
    print(message)


def _record_process_identity(pid: int) -> None:
    identity = process_birth_identity(pid)
    path = PID_FILE.with_name(".bot.identity.json")
    if identity is not None:
        path.write_text(json.dumps({"pid": pid, "profile_id": PROFILE_ID, "birth": identity}), encoding="utf-8")
    else:
        path.unlink(missing_ok=True)


def _worker_identity(pid: int) -> bool | None:
    # An existing snapshot takes precedence over any reused HTTP endpoint.
    identity_path = PID_FILE.with_name(".bot.identity.json")
    if identity_path.exists():
        return recorded_process_identity(PID_FILE.parent, pid, PROFILE_ID)
    from services.desktop_status import read_health
    port = _read_port()
    health = read_health(WEBAPP_HOST, port) if port else {}
    if health.get("pid") == pid:
        if health.get("profile_id") == PROFILE_ID:
            return True
        if health.get("profile_id") is None and PROFILE_ID == "personal":
            from services.bot_profiles import get_profile
            if get_profile(PROFILE_ID, base_dir=BASE_DIR).legacy:
                return True
    if isinstance(health.get("pid"), int) and isinstance(health.get("profile_id"), str):
        return False
    return None


def _read_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def _read_tray_pid() -> int | None:
    if not TRAY_PID_FILE.exists():
        return None
    try:
        return int(TRAY_PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def _write_pid(pid: int) -> None:
    _record_process_identity(pid)
    PID_FILE.write_text(str(pid), encoding="utf-8")


def _write_tray_pid(pid: int) -> None:
    TRAY_PID_FILE.write_text(str(pid), encoding="utf-8")


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
    PID_FILE.with_name(".bot.identity.json").unlink(missing_ok=True)
    if PID_FILE.exists():
        PID_FILE.unlink()


def _clear_port() -> None:
    if PORT_FILE.exists():
        PORT_FILE.unlink()


def _clear_tray_pid() -> None:
    if TRAY_PID_FILE.exists():
        TRAY_PID_FILE.unlink()


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


def _profile_port_claimed(port: int) -> bool:
    from services.bot_profiles import list_profiles
    for profile in list_profiles(base_dir=BASE_DIR):
        if profile.id == PROFILE_ID:
            continue
        runtime = profile.runtime_dir(BASE_DIR)
        try:
            claimed_port = int((runtime / ".bot.port").read_text(encoding="utf-8").strip())
            pid = int((runtime / ".bot.pid").read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            continue
        if claimed_port == port and _is_running(pid):
            return True
    return False


def _select_webapp_port(start_port: int) -> int:
    for port in range(start_port, 65536):
        if _is_port_free(port) and not _profile_port_claimed(port):
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
    env["BOT_BUDGET_PROFILE"] = PROFILE_ID
    env["BOT_BUDGET_WEBAPP_HOST"] = WEBAPP_HOST
    env["BOT_BUDGET_WEBAPP_PORT"] = str(port)
    env["BOT_BUDGET_WEBAPP_URL"] = _build_runtime_webapp_url(port)
    return env


def _get_windowless_python() -> str:
    if os.name != "nt":
        return sys.executable

    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if pythonw.exists():
        return str(pythonw)
    return sys.executable


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


def _start_with_port_reservation(background: bool) -> None:
    # Different profile managers have different start locks, but allocate from
    # the same host port range. Hold this lock through publishing PID and port.
    lock = ProcessLock(BASE_DIR / ".ports-start.lock")
    deadline = time.monotonic() + 10
    while not lock.acquire():
        if time.monotonic() >= deadline:
            _failure("Another profile is allocating its Web App port. Retry start shortly.")
            return
        time.sleep(0.05)
    try:
        foreground = _start_bot(background)
    finally:
        lock.release()
    if foreground is not None:
        try:
            returncode = foreground.wait()
            if returncode:
                _failure(f"Bot exited with status {returncode}.")
        finally:
            if _read_pid() == foreground.pid:
                _clear_pid()
                _clear_port()


def start_bot(background: bool = True) -> None:
    try:
        with ProcessLock(START_LOCK_FILE):
            _start_with_port_reservation(background)
    except AlreadyRunningError:
        _failure("Bot start is already in progress.")


def _start_bot(background: bool = True) -> subprocess.Popen | None:
    pid = _read_pid()
    if pid and _is_running(pid):
        ownership = _worker_identity(pid)
        if ownership is True:
            print(f"Bot is already running (PID {pid}).")
            return
        if ownership is None:
            _failure(f"PID {pid} is active but ownership by profile {PROFILE_ID} is unknown. Check the profile log before retrying.")
            return
        print(f"Ignoring stale PID {pid}; it belongs to another process.")
        _clear_pid()
        _clear_port()
    if is_lock_held(BOT_LOCK_FILE):
        print("Bot is already running (runtime lock is held).")
        return

    runtime_port = WEBAPP_PORT
    if _is_webapp_port_busy() or _profile_port_claimed(runtime_port):
        try:
            runtime_port = _select_webapp_port(WEBAPP_PORT + 1)
        except RuntimeError as exc:
            _failure(str(exc))
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
        start_tray(silent=True)
        return

    print("Starting in foreground. Stop with Ctrl+C")
    process = subprocess.Popen(
        [sys.executable, "bot.py"],
        cwd=str(BASE_DIR),
        env=_build_runtime_env(runtime_port),
    )
    _write_pid(process.pid)
    _write_port(runtime_port)
    return process


def stop_bot() -> None:
    pid = _read_pid()
    if not pid:
        print("PID file not found. Bot is probably not running in background.")
        return

    if not _is_running(pid):
        print("Process is not active. Cleaning PID file.")
        _clear_pid()
        return

    if _worker_identity(pid) is not True:
        _failure(f"Cannot verify PID {pid} belongs to profile {PROFILE_ID}; process was not stopped. "
              "Check the profile log and retry when its health endpoint is available.")
        return

    try:
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if result.returncode != 0:
                _failure(f"Failed to stop PID {pid}; process metadata was preserved.")
                return
        else:
            os.kill(pid, signal.SIGTERM)
        print(f"Bot stopped (PID {pid}).")
    except OSError as exc:
        _failure(f"Failed to stop PID {pid}: {type(exc).__name__}.")
        return
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
        ownership = _worker_identity(pid)
        if ownership is True:
            print(f"Bot is running in background (PID {pid}, Web App port {runtime_port}).")
        elif ownership is False:
            _failure(f"Stored PID {pid} belongs to another process; profile {PROFILE_ID} is not verified running.")
        else:
            _failure(f"PID {pid} is active but ownership by profile {PROFILE_ID} is unknown.")
    else:
        if not _is_port_free(runtime_port):
            print(
                f"PID file exists, bot process is not active, but "
                f"Web App port {WEBAPP_HOST}:{runtime_port} is busy."
            )
        else:
            print("PID file exists, but process is not active.")


def start_tray(silent: bool = False) -> None:
    try:
        with ProcessLock(TRAY_START_LOCK_FILE):
            _start_tray(silent)
    except AlreadyRunningError:
        if not silent:
            print("Tray start is already in progress.")


def _start_tray(silent: bool = False) -> None:
    if is_lock_held(TRAY_LOCK_FILE):
        if not silent:
            print("Tray icon is already running (runtime lock is held).")
        return
    tray_pid = _read_tray_pid()
    if tray_pid and _is_running(tray_pid):
        if not silent:
            print(f"Tray icon is already running (PID {tray_pid}).")
        return
    if tray_pid:
        _clear_tray_pid()

    with (BASE_DIR / "bot.log").open("a", encoding="utf-8") as log_file:
        kwargs = {
            "stdout": log_file,
            "stderr": log_file,
            "cwd": str(BASE_DIR),
            "env": _shared_runtime_env(),
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        process = subprocess.Popen([_get_windowless_python(), "tray_monitor.py"], **kwargs)

    _write_tray_pid(process.pid)
    if not silent:
        print(f"Tray icon started (PID {process.pid}).")


def stop_tray() -> None:
    tray_pid = _read_tray_pid()
    if not tray_pid:
        print("Tray PID file not found. Tray icon is probably not running.")
        return

    if not _is_running(tray_pid):
        print("Tray process is not active. Cleaning tray PID file.")
        _clear_tray_pid()
        return

    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(tray_pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            os.kill(tray_pid, signal.SIGTERM)
        print(f"Tray icon stopped (PID {tray_pid}).")
    finally:
        _clear_tray_pid()


def restart_bot() -> None:
    stop_bot()
    if EXIT_CODE == 0:
        start_bot(background=True)


def start_desktop(minimized: bool = False, start_bot_on_open: bool = False) -> None:
    try:
        with ProcessLock(DESKTOP_START_LOCK_FILE):
            start_tray(silent=True)
            try:
                desktop_pid = int(DESKTOP_PID_FILE.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                desktop_pid = None
            if is_lock_held(DESKTOP_LOCK_FILE) or (desktop_pid and _is_running(desktop_pid)):
                if start_bot_on_open or not minimized:
                    request = "start" if minimized else "show-and-start" if start_bot_on_open else "show"
                    DESKTOP_SHOW_FILE.write_text(request, encoding="utf-8")
                print("Desktop panel is already running.")
                return
            command = [_get_windowless_python(), str(BASE_DIR / "desktop_app.py")]
            if minimized:
                command.append("--minimized")
            if start_bot_on_open:
                command.append("--start-bot")
            kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
            with (BASE_DIR / "bot.log").open("a", encoding="utf-8") as log_file:
                process = subprocess.Popen(command, cwd=BASE_DIR, stdout=log_file, stderr=log_file, env=_shared_runtime_env(), **kwargs)
            DESKTOP_PID_FILE.write_text(str(process.pid), encoding="utf-8")
            print(f"Desktop panel started (PID {process.pid}).")
    except AlreadyRunningError:
        if start_bot_on_open or not minimized:
            request = "start" if minimized else "show-and-start" if start_bot_on_open else "show"
            DESKTOP_SHOW_FILE.write_text(request, encoding="utf-8")
        print("Desktop panel start is already in progress.")


def main() -> int:
    global EXIT_CODE
    EXIT_CODE = 0
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
    sub.add_parser("tray", help="Start tray status icon")
    sub.add_parser("stop-tray", help="Stop tray status icon")
    desktop_parser = sub.add_parser("ui", help="Open Windows control panel")
    desktop_parser.add_argument("--minimized", action="store_true")
    desktop_parser.add_argument("--start-bot", action="store_true")

    sub.add_parser("start-autostart", help="Start panel and enabled profiles")
    sub.add_parser("prepare-update", help="Remember and stop active profiles before updating")
    sub.add_parser("finish-update", help="Restart and verify profiles remembered before updating")
    for name in ("start", "stop", "restart", "status"):
        command_parser = sub.choices[name]
        selection = command_parser.add_mutually_exclusive_group()
        selection.add_argument("--profile", default="personal")
        selection.add_argument("--all", action="store_true")

    args = parser.parse_args()
    if args.command in {"prepare-update", "finish-update"}:
        from services.update_runtime import prepare, finish
        try:
            (prepare if args.command == "prepare-update" else finish)(sys.modules[__name__])
        except (RuntimeError, OSError, ValueError) as error:
            _failure(str(error))
        return EXIT_CODE
    if args.command == "start-autostart":
        start_autostart()
        return EXIT_CODE
    if args.command in {"start", "stop", "restart", "status"}:
        if args.all:
            if args.command == "start" and args.foreground:
                parser.error("--all cannot be combined with --foreground")
            from services.bot_profiles import list_profiles
            for profile in list_profiles(base_dir=BASE_DIR):
                configure_profile(profile.id)
                print(f"[{profile.id}]")
                if args.command == "start":
                    start_bot(background=True)
                else:
                    {"stop": stop_bot, "restart": restart_bot, "status": status_bot}[args.command]()
            return EXIT_CODE
        configure_profile(args.profile)

    if args.command == "ui":
        start_desktop(minimized=args.minimized, start_bot_on_open=args.start_bot)
        return EXIT_CODE
    if args.command == "start":
        start_bot(background=not args.foreground)
        return EXIT_CODE
    if args.command == "stop":
        stop_bot()
        return EXIT_CODE
    if args.command == "restart":
        restart_bot()
        return EXIT_CODE
    if args.command == "status":
        status_bot()
        return EXIT_CODE
    if args.command == "tray":
        start_tray()
        return EXIT_CODE
    if args.command == "stop-tray":
        stop_tray()
        return EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
