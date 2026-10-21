"""Read-only desktop monitoring. Never reads credentials or calls bot APIs."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import time
from urllib.error import HTTPError
import urllib.request

from services.process_control import is_direct_child, is_process_running, recorded_process_identity


@dataclass(frozen=True)
class ConnectionStatus:
    reachable: bool
    latency_ms: int | None = None


@dataclass(frozen=True)
class DesktopStatus:
    state: str
    pid: int | None
    version: str
    uptime_seconds: int | None
    telegram: ConnectionStatus
    google: ConnectionStatus
    checked_at: datetime
    profile_id: str = "personal"


def read_int(path: Path) -> int | None:
    try:
        value = int(path.read_text(encoding="utf-8").strip())
        return value if value > 0 else None
    except (OSError, ValueError):
        return None


def probe_service(url: str, timeout: float = 2.5) -> ConnectionStatus:
    started = time.monotonic()
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "BotBudgetMonitor"})
    try:
        with urllib.request.urlopen(request, timeout=timeout):
            pass
    except HTTPError as exc:
        # An HTTP response (including 401/404) proves HTTPS reachability,
        # not authorization or access to any specific Google spreadsheet.
        status = exc.code
        exc.close()
        if status >= 500:
            return ConnectionStatus(False)
    except (OSError, ValueError):
        return ConnectionStatus(False)
    return ConnectionStatus(True, round((time.monotonic() - started) * 1000))


def read_health(host: str, port: int, timeout: float = 1.5) -> dict:
    host = {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(host, host)
    host = f"[{host}]" if ":" in host and not host.startswith("[") else host
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/webapp/health", timeout=timeout) as response:
            payload = json.loads(response.read(16384))
            return payload if isinstance(payload, dict) and payload.get("ok") is True else {}
    except (OSError, ValueError):
        return {}


def collect_status(base_dir: Path, host: str, default_port: int, installed_version: str, profile_id: str = "personal") -> DesktopStatus:
    from services.bot_profiles import get_profile
    profile = get_profile(profile_id, base_dir=base_dir)
    base_dir = profile.runtime_dir(base_dir)
    stored_pid = read_int(base_dir / ".bot.pid")
    port = read_int(base_dir / ".bot.port") or default_port
    if not 1 <= port <= 65535:
        port = default_port
    with ThreadPoolExecutor(max_workers=3) as executor:
        telegram = executor.submit(probe_service, "https://api.telegram.org/")
        google = executor.submit(probe_service, "https://sheets.googleapis.com/")
        local = executor.submit(read_health, host, port)
        health = local.result()
        telegram_status, google_status = telegram.result(), google.result()

    # A port can be reused by another profile or application. Never borrow its
    # PID/version/uptime, even when the selected worker's PID file is absent.
    identity = health.get("profile_id")
    # Windows venv python.exe can stay alive as a launcher while its child
    # serves HTTP. Keep the recorded launcher's PID for process controls, but
    # accept readiness only after verifying ownership and the OS parent link.
    endpoint_pid = health.get("pid")
    if (stored_pid and isinstance(endpoint_pid, int)
            and identity in (None, profile_id)
            and recorded_process_identity(base_dir, stored_pid, profile_id) is True
            and (endpoint_pid == stored_pid or is_direct_child(endpoint_pid, stored_pid))):
        identity = profile_id
        health = dict(health, pid=stored_pid, profile_id=profile_id)
    foreign_health = bool(identity is not None and (identity != profile_id or (stored_pid and health.get("pid") != stored_pid)))
    if identity != profile_id and not (identity is None and profile.legacy):
        health = {}
    health_pid = health.get("pid")
    if identity is not None and stored_pid and health_pid != stored_pid:
        health = {}
        health_pid = None
    pid = health_pid if isinstance(health_pid, int) and health_pid > 0 else stored_pid
    ownership = recorded_process_identity(base_dir, pid, profile_id) if pid else None
    alive = bool(pid and is_process_running(pid) and ownership is not False
                 and not (foreign_health and ownership is not True))
    if alive and health and health.get("polling_ready", True):
        state = "running" if telegram_status.reachable and google_status.reachable else "offline"
    elif alive:
        state = "starting"
    else:
        state = "stopped"
    uptime = health.get("uptime_seconds")
    if not isinstance(uptime, (int, float)) or uptime < 0:
        uptime = None
    return DesktopStatus(
        state=state, pid=pid if alive else None,
        version=str(health.get("version") or installed_version),
        uptime_seconds=int(uptime) if uptime is not None else None,
        telegram=telegram_status, google=google_status, checked_at=datetime.now(), profile_id=profile_id,
    )


def format_uptime(seconds: int | None) -> str:
    if seconds is None:
        return "—"
    hours, remainder = divmod(seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    if hours >= 24:
        days, hours = divmod(hours, 24)
        return f"{days} д {hours} ч"
    return f"{hours} ч {minutes:02d} мин" if hours else f"{minutes} мин"
