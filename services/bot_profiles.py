"""Non-secret budget profile registry; separate processes own runtime state."""
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import tempfile
import time
from zoneinfo import ZoneInfo

from services.profile_secrets import load_token, save_token
from services.process_control import ProcessLock

BASE_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class BotProfile:
    id: str
    name: str
    spreadsheet_id: str
    currency: str = "EUR"
    timezone: str = "Europe/Moscow"
    autostart: bool = False
    credentials_file: str = ""
    legacy: bool = False
    track_money_source: bool = False

    def runtime_dir(self, base_dir: Path = BASE_DIR) -> Path:
        return Path(base_dir) if self.legacy else Path(base_dir) / ".runtime" / self.id


def _validate(profile: BotProfile) -> None:
    if type(profile.track_money_source) is not bool:
        raise ValueError("track_money_source must be a boolean.")
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", profile.id):
        raise ValueError("Profile id must contain lowercase letters, digits, underscores or hyphens.")
    if not profile.name.strip():
        raise ValueError("Profile name is required.")
    if profile.currency not in {"EUR", "RUB"}:
        raise ValueError("Profile currency must be EUR or RUB.")
    ZoneInfo(profile.timezone)
    if profile.legacy and profile.id != "personal":
        raise ValueError("Only the personal profile can use legacy configuration.")
    if not profile.legacy and not profile.spreadsheet_id.strip():
        raise ValueError("Profile spreadsheet is required.")


def list_profiles(base_dir: Path = BASE_DIR) -> list[BotProfile]:
    path = Path(base_dir) / "profiles.json"
    if not path.exists():
        return [BotProfile("personal", "Личный бюджет", "", legacy=True)]
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        profiles = [BotProfile(**item) for item in raw["profiles"]]
        seen = set()
        for profile in profiles:
            _validate(profile)
            if profile.id in seen:
                raise ValueError()
            seen.add(profile.id)
        return profiles or [BotProfile("personal", "Личный бюджет", "", legacy=True)]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise ValueError("Не удалось прочитать profiles.json. Восстановите корректный файл из резервной копии; профили не изменены.") from None


def get_profile(profile_id: str, base_dir: Path = BASE_DIR) -> BotProfile:
    for profile in list_profiles(base_dir):
        if profile.id == profile_id:
            return profile
    raise ValueError("Unknown budget profile.")


def get_profile_token(profile: BotProfile, base_dir: Path = BASE_DIR) -> str:
    if profile.legacy:
        # Lazy import avoids a config/profile import cycle.
        import config
        if not config.PROFILE.legacy:
            raise ValueError("Legacy token unavailable in a non-legacy runtime.")
        return config.BOT_TOKEN
    return load_token(profile.id, Path(base_dir))


def _save(profile: BotProfile, token: str | None, base_dir: Path, *, editing: bool) -> BotProfile:
    base_dir.mkdir(parents=True, exist_ok=True)
    lock = ProcessLock(base_dir / ".profiles.lock")
    deadline = time.monotonic() + 5
    while not lock.acquire():
        if time.monotonic() >= deadline:
            raise ValueError("Реестр профилей занят. Повторите сохранение.")
        time.sleep(0.02)
    try:
        return _save_locked(profile, token, base_dir, editing=editing)
    finally:
        lock.release()


def _save_locked(profile: BotProfile, token: str | None, base_dir: Path, *, editing: bool) -> BotProfile:
    _validate(profile)
    profiles = list_profiles(base_dir)
    existing = next((p for p in profiles if p.id == profile.id), None)
    if (existing is not None) != editing:
        raise ValueError("Profile already exists." if existing else "Profile does not exist.")
    if existing and existing.legacy != profile.legacy:
        raise ValueError("Legacy profile mode cannot be changed.")
    if token is not None:
        token = token.strip()
        if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", token):
            raise ValueError("Invalid Telegram bot token format.")
    identity = token.split(":", 1)[0] if token else None
    for other in profiles:
        if other.id == profile.id:
            continue
        other_spreadsheet = other.spreadsheet_id
        if other.legacy:
            import config
            if config.PROFILE.legacy:
                other_spreadsheet = config.SPREADSHEET_ID
        if profile.spreadsheet_id and profile.spreadsheet_id == other_spreadsheet:
            raise ValueError("A spreadsheet cannot be shared by budget profiles.")
        if identity:
            other_token = get_profile_token(other, base_dir)
            if other_token and identity == other_token.split(":", 1)[0]:
                raise ValueError("This Telegram bot is already assigned to another profile.")
    if not profile.legacy and token is None and not load_token(profile.id, base_dir):
        raise ValueError("A protected Telegram token is required.")
    if token is not None and profile.legacy:
        raise ValueError("Legacy token is managed by existing environment configuration.")
    values = [profile if p.id == profile.id else p for p in profiles]
    if existing is None:
        values.append(profile)
    base_dir.mkdir(parents=True, exist_ok=True)
    secret_path = base_dir / ".profile-secrets" / (profile.id + ".bin")
    previous_secret = secret_path.read_bytes() if token is not None and secret_path.exists() else None
    fd, filename = tempfile.mkstemp(dir=base_dir, prefix=".profiles-", suffix=".tmp")
    token_changed = False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"version": 1, "profiles": [asdict(p) for p in values]}, stream, ensure_ascii=False, indent=2)
        if token is not None:
            save_token(profile.id, token, base_dir)
            token_changed = True
        os.replace(filename, base_dir / "profiles.json")
    except BaseException:
        if token_changed:
            if previous_secret is None:
                secret_path.unlink(missing_ok=True)
            else:
                rollback_fd, rollback_name = tempfile.mkstemp(dir=secret_path.parent)
                try:
                    with os.fdopen(rollback_fd, "wb") as stream:
                        stream.write(previous_secret)
                    os.replace(rollback_name, secret_path)
                finally:
                    Path(rollback_name).unlink(missing_ok=True)
        raise
    finally:
        Path(filename).unlink(missing_ok=True)
    return profile


def save_profile(profile: BotProfile, *, token: str | None = None, base_dir: Path = BASE_DIR) -> BotProfile:
    return _save(profile, token, Path(base_dir), editing=False)


def update_profile(profile: BotProfile, *, token: str | None = None, base_dir: Path = BASE_DIR) -> BotProfile:
    return _save(profile, token, Path(base_dir), editing=True)
