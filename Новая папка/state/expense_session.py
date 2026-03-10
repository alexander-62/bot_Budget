import time
from dataclasses import dataclass

from constants import EXPENSE_SESSION_TTL_SECONDS


@dataclass
class ExpenseSession:
    session_id: str
    state: str
    category: str | None = None
    subcategory: str | None = None
    amount: str | None = None
    prompt_chat_id: int | None = None
    prompt_message_id: int | None = None
    updated_at: float = 0.0
    finalized: bool = False


_expense_sessions: dict[int, ExpenseSession] = {}


def new_session_id() -> str:
    return str(int(time.time() * 1000))


def create_session(user_id: int, state: str) -> ExpenseSession:
    session = ExpenseSession(
        session_id=new_session_id(),
        state=state,
        updated_at=time.monotonic(),
    )
    _expense_sessions[user_id] = session
    return session


def get_active_session(user_id: int) -> ExpenseSession | None:
    session = _expense_sessions.get(user_id)
    if session is None:
        return None
    if time.monotonic() - session.updated_at > EXPENSE_SESSION_TTL_SECONDS:
        _expense_sessions.pop(user_id, None)
        return None
    return session


def pop_session(user_id: int) -> ExpenseSession | None:
    return _expense_sessions.pop(user_id, None)


def touch_session(session: ExpenseSession) -> None:
    session.updated_at = time.monotonic()


def is_stale_session(user_id: int, session_id: str) -> bool:
    session = get_active_session(user_id)
    if session is None:
        return True
    return session.session_id != session_id or session.finalized

