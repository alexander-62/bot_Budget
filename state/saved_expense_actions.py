import time
from dataclasses import dataclass
from uuid import uuid4

from services.expenses import SavedExpense

_SAVED_EXPENSE_ACTION_TTL_SECONDS = 1800


@dataclass
class SavedExpenseAction:
    action_id: str
    user_id: int
    saved_expense: SavedExpense
    updated_at: float
    active: bool = True


_actions_by_user: dict[int, SavedExpenseAction] = {}


def new_action_id() -> str:
    return uuid4().hex


def create_saved_expense_action(user_id: int, saved_expense: SavedExpense) -> SavedExpenseAction:
    action = SavedExpenseAction(
        action_id=new_action_id(),
        user_id=user_id,
        saved_expense=saved_expense,
        updated_at=time.monotonic(),
    )
    _actions_by_user[user_id] = action
    return action


def get_saved_expense_action(user_id: int) -> SavedExpenseAction | None:
    action = _actions_by_user.get(user_id)
    if action is None:
        return None
    if time.monotonic() - action.updated_at > _SAVED_EXPENSE_ACTION_TTL_SECONDS:
        _actions_by_user.pop(user_id, None)
        return None
    if not action.active:
        return None
    return action


def is_stale_saved_expense_action(user_id: int, action_id: str) -> bool:
    action = get_saved_expense_action(user_id)
    if action is None:
        return True
    return action.action_id != action_id


def touch_saved_expense_action(action: SavedExpenseAction) -> None:
    action.updated_at = time.monotonic()


def update_saved_expense_action(user_id: int, saved_expense: SavedExpense) -> SavedExpenseAction | None:
    action = get_saved_expense_action(user_id)
    if action is None:
        return None
    action.saved_expense = saved_expense
    touch_saved_expense_action(action)
    return action


def finalize_saved_expense_action(user_id: int) -> None:
    action = _actions_by_user.get(user_id)
    if action is not None:
        action.active = False
        _actions_by_user.pop(user_id, None)
