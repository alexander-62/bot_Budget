from dataclasses import dataclass, field
from time import monotonic
from uuid import uuid4

TTL_SECONDS = 900


@dataclass
class SettingsSession:
    chat_id: int
    token: str = field(default_factory=lambda: uuid4().hex[:12])
    step: str = "menu"
    category: str = ""
    categories: tuple[str, ...] = ()
    currency: str = ""
    updated_at: float = field(default_factory=monotonic)


_sessions: dict[int, SettingsSession] = {}


def create_session(user_id, chat_id):
    session = SettingsSession(chat_id)
    _sessions[user_id] = session
    return session


def pop_session(user_id):
    return _sessions.pop(user_id, None)


def get_session(user_id):
    session = _sessions.get(user_id)
    if session and monotonic() - session.updated_at > TTL_SECONDS:
        pop_session(user_id)
        return None
    return session


def advance(session, step):
    session.step = step
    session.token = uuid4().hex[:12]
    session.updated_at = monotonic()
