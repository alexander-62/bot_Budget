import sys
import types
import unittest


if "gspread" not in sys.modules:
    fake_gspread = types.ModuleType("gspread")

    class _Client:
        pass

    class _Spreadsheet:
        pass

    class _Worksheet:
        pass

    fake_gspread.Client = _Client
    fake_gspread.Spreadsheet = _Spreadsheet
    fake_gspread.Worksheet = _Worksheet
    fake_gspread.service_account = lambda filename=None: None
    sys.modules["gspread"] = fake_gspread

fake_aiogram = sys.modules.get("aiogram")
fake_types = sys.modules.get("aiogram.types")
if fake_aiogram is None:
    fake_aiogram = types.ModuleType("aiogram")
    fake_aiogram.__path__ = []
    sys.modules["aiogram"] = fake_aiogram

if fake_types is None:
    fake_types = types.ModuleType("aiogram.types")
    sys.modules["aiogram.types"] = fake_types

if not hasattr(fake_types, "InlineKeyboardButton"):
    class InlineKeyboardButton:
        def __init__(self, text: str, callback_data: str | None = None, **kwargs) -> None:
            self.text = text
            self.callback_data = callback_data
            self.extra = kwargs

    fake_types.InlineKeyboardButton = InlineKeyboardButton

if not hasattr(fake_types, "InlineKeyboardMarkup"):
    class InlineKeyboardMarkup:
        def __init__(self, inline_keyboard):
            self.inline_keyboard = inline_keyboard

    fake_types.InlineKeyboardMarkup = InlineKeyboardMarkup

fake_aiogram.types = fake_types

from keyboards.expenses import build_saved_expense_actions_keyboard, build_saved_expense_edit_keyboard
from services.expenses import SavedExpense
from state.saved_expense_actions import (
    create_saved_expense_action,
    finalize_saved_expense_action,
    get_saved_expense_action,
    is_stale_saved_expense_action,
    update_saved_expense_action,
)


def _sample_saved_expense() -> SavedExpense:
    return SavedExpense(
        expense_id="exp-1",
        sheet_name="Траты_по_месяцам",
        row_number=10,
        row_range="Траты_по_месяцам!A10:H10",
        date="2026-06-29",
        month_key="2026-06",
        username="@alice",
        category="Еда",
        subcategory="Кафе",
        amount="12,50",
        comment="латте",
    )


class Phase7SavedActionTests(unittest.TestCase):
    def test_saved_action_replaces_old_action_for_same_user(self) -> None:
        first = create_saved_expense_action(1, _sample_saved_expense())
        second_expense = _sample_saved_expense()
        second_expense = SavedExpense(**{**second_expense.__dict__, "expense_id": "exp-2"})
        second = create_saved_expense_action(1, second_expense)

        self.assertTrue(is_stale_saved_expense_action(1, first.action_id))
        self.assertFalse(is_stale_saved_expense_action(1, second.action_id))

    def test_saved_action_can_be_updated_and_finalized(self) -> None:
        action = create_saved_expense_action(2, _sample_saved_expense())
        updated = SavedExpense(**{**action.saved_expense.__dict__, "amount": "15,00", "comment": "капучино"})

        update_saved_expense_action(2, updated)
        current = get_saved_expense_action(2)
        self.assertIsNotNone(current)
        self.assertEqual(current.saved_expense.amount, "15,00")
        self.assertEqual(current.saved_expense.comment, "капучино")

        finalize_saved_expense_action(2)
        self.assertIsNone(get_saved_expense_action(2))

    def test_saved_expense_keyboards_have_expected_callbacks(self) -> None:
        keyboard = build_saved_expense_actions_keyboard("42")
        edit_keyboard = build_saved_expense_edit_keyboard("42")

        action_callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
        edit_callbacks = [button.callback_data for row in edit_keyboard.inline_keyboard for button in row]

        self.assertEqual(
            action_callbacks,
            ["exp:saved:edit:42", "exp:saved:repeat:42", "exp:saved:fresh:42"],
        )
        self.assertEqual(edit_callbacks, ["exp:saved:delete:42", "exp:saved:cancel:42"])


if __name__ == "__main__":
    unittest.main()
