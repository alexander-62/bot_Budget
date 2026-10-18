"""Read-only desktop monitoring. Never reads credentials or calls bot APIs."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import time
from urllib.error import HTTPError
import urllib.request

from services.process_control import is_process_running


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


def collect_status(base_dir: Path, host: str, default_port: int, installed_version: str) -> DesktopStatus:
    port = read_int(base_dir / ".bot.port") or default_port
    if not 1 <= port <= 65535:
        port = default_port
    with ThreadPoolExecutor(max_workers=3) as executor:
        telegram = executor.submit(probe_service, "https://api.telegram.org/")
        google = executor.submit(probe_service, "https://sheets.googleapis.com/")
        local = executor.submit(read_health, host, port)
        health = local.result()
        telegram_status, google_status = telegram.result(), google.result()

    health_pid = health.get("pid")
    pid = health_pid if isinstance(health_pid, int) and health_pid > 0 else read_int(base_dir / ".bot.pid")
    alive = bool(pid and is_process_running(pid))
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
        telegram=telegram_status, google=google_status, checked_at=datetime.now(),
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
