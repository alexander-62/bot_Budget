import time
from dataclasses import dataclass

from constants import SHOPPING_SESSION_TTL_SECONDS


@dataclass
class ShoppingSession:
    session_id: str
    state: str
    list_chat_id: int | None = None
    list_message_id: int | None = None
    step_chat_id: int | None = None
    step_message_id: int | None = None
    updated_at: float = 0.0
    finalized: bool = False


_shopping_sessions: dict[int, ShoppingSession] = {}


def _new_session_id() -> str:
    return str(int(time.time() * 1000))


def create_session(user_id: int, state: str) -> ShoppingSession:
    session = ShoppingSession(
        session_id=_new_session_id(),
        state=state,
        updated_at=time.monotonic(),
    )
    _shopping_sessions[user_id] = session
    return session


def get_active_session(user_id: int) -> ShoppingSession | None:
    session = _shopping_sessions.get(user_id)
    if session is None:
        return None
    if time.monotonic() - session.updated_at > SHOPPING_SESSION_TTL_SECONDS:
        _shopping_sessions.pop(user_id, None)
        return None
    return session


def pop_session(user_id: int) -> ShoppingSession | None:
    return _shopping_sessions.pop(user_id, None)


def touch_session(session: ShoppingSession) -> None:
    session.updated_at = time.monotonic()


def is_stale_session(user_id: int, session_id: str) -> bool:
    session = get_active_session(user_id)
    if session is None:
        return True
    return session.session_id != session_id or session.finalized
