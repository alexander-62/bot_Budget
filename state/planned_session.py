from dataclasses import dataclass, field
from time import monotonic
from uuid import uuid4


@dataclass
class PlannedSession:
    chat_id: int
    token: str = field(default_factory=lambda: uuid4().hex[:10])
    step: str = 'list'
    values: dict = field(default_factory=dict)
    options: tuple = ()
    record: object = None
    new_id: str = field(default_factory=lambda: uuid4().hex)
    editing: bool = False
    history: bool = False
    page: int = 0
    owner_id: int = 0
    owner_username: str | None = None
    updated_at: float = field(default_factory=monotonic)


_sessions = {}


def create_session(user_id, chat_id):
    session = PlannedSession(chat_id, owner_id=user_id)
    _sessions[user_id] = session
    return session


def pop_session(user_id):
    return _sessions.pop(user_id, None)


def clear_sessions() -> None:
    _sessions.clear()


def get_session(user_id):
    session = _sessions.get(user_id)
    if session and monotonic() - session.updated_at > 900:
        pop_session(user_id)
        return None
    return session


def advance(session, step):
    session.step = step
    session.token = uuid4().hex[:10]
    session.updated_at = monotonic()
