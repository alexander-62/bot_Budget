import asyncio
from contextlib import ExitStack
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import config
from handlers import expenses
from services.expenses import SavedExpense
from state.expense_session import create_session, get_active_session, pop_session
from state.saved_expense_actions import create_saved_expense_action, get_saved_expense_action, finalize_saved_expense_action


def saved(source=""):
    return SavedExpense("id", "sheet", 2, "A2:I2", "2026-10-21", "2026-10", "@user", "Food", "Shop", "12", "comment", source)


class MoneySourceFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(expenses, "TRACK_MONEY_SOURCE", True))
        self.stack.enter_context(patch.object(expenses, "check_access_callback", AsyncMock(return_value=True)))
        self.stack.enter_context(patch.object(expenses, "_show_category_card", AsyncMock()))
        self.sources = ["Card <A>", "Cash"]
        self.writes, self.updates = [], []
        self.source_reads = 0
        self.stack.enter_context(patch.object(expenses, "run_blocking", self.run_service))
        self.prompt = SimpleNamespace(chat=SimpleNamespace(id=101), message_id=10)
        self.message = SimpleNamespace(answer=AsyncMock(return_value=self.prompt),
                                       bot=SimpleNamespace(delete_message=AsyncMock()))

    async def asyncTearDown(self):
        self.stack.close()
        for user_id in (101, 202):
            pop_session(user_id)
            finalize_saved_expense_action(user_id)

    async def run_service(self, function, *args, **kwargs):
        if function is expenses.get_money_sources:
            self.source_reads += 1
            return list(self.sources)
        if function in (expenses.is_allowed_username, expenses.is_allowed_user):
            return True, ""
        if function is expenses.get_subcategories_for_category:
            return ["Shop"]
        if function is expenses.write_expense:
            self.writes.append(kwargs)
            return replace(saved(), **kwargs)
        if function is expenses.update_expense:
            self.updates.append((args, kwargs))
            return replace(args[0], amount=args[1], comment=args[2], **kwargs)
        raise AssertionError(function)

    def callback(self, data, user_id=101):
        return SimpleNamespace(data=data, from_user=SimpleNamespace(id=user_id, username="user"),
                               answer=AsyncMock(), message=self.message, bot=self.message.bot)

    async def choose(self, session, index=0):
        await expenses.expense_source_handler(self.callback(f"exp:src:{session.session_id}:{index}"))

    async def test_enabled_subcategory_source_amount_save(self):
        session = create_session(101, "choose_subcategory")
        session.category = "Food"
        await expenses.expense_subcategory_handler(self.callback(f"exp:sub:{session.session_id}:0"))
        self.assertEqual(session.state, "choose_source")
        await self.choose(session)
        self.assertEqual(session.state, "enter_amount")
        session.amount = "12"
        await expenses._finalize_expense(101, "user", self.message)
        self.assertEqual(self.writes[0]["money_source"], "Card <A>")
        self.assertIn("Card &lt;A&gt;", self.message.answer.call_args_list[-1].args[0])

    async def test_disabled_path_does_not_read_sources_or_change_write_signature(self):
        with patch.object(expenses, "TRACK_MONEY_SOURCE", False):
            await expenses._show_repeat_expense_amount_step(self.message, 101, "Food", "Shop")
            session = get_active_session(101)
            self.assertEqual(session.state, "enter_amount")
            session.amount = "12"
            await expenses._finalize_expense(101, "user", self.message)
        self.assertEqual(self.source_reads, 0)
        self.assertNotIn("money_source", self.writes[0])

    async def test_snapshot_survives_reordering_and_repeat_asks_again(self):
        await expenses._show_repeat_expense_amount_step(self.message, 101, "Food", "Shop")
        session = get_active_session(101)
        self.assertEqual(session.state, "choose_source")
        self.sources.reverse()
        await self.choose(session)
        self.assertEqual(session.money_source, "Card <A>")

    async def test_refreshed_picker_rejects_old_indices_before_saved_update(self):
        self.sources = ["Cash", "Card"]
        action = create_saved_expense_action(101, saved("Cash"))
        await expenses.saved_expense_action_handler(self.callback(f"exp:saved:source:{action.action_id}"))
        session = get_active_session(101)
        old_picker_id = session.session_id
        old_cash_callback = f"exp:src:{old_picker_id}:0"
        self.sources = ["Card"]
        await expenses.expense_source_handler(self.callback(old_cash_callback))
        self.assertNotEqual(session.session_id, old_picker_id)
        self.assertEqual(session.source_options, ("Card",))
        self.message.bot.delete_message.assert_awaited_with(chat_id=101, message_id=10)
        reads = self.source_reads
        await expenses.expense_source_handler(self.callback(old_cash_callback))
        self.assertEqual(self.source_reads, reads)
        self.assertFalse(self.updates)
        self.assertFalse(self.writes)
        await self.choose(session, 0)
        self.assertEqual(self.updates[0][1], {"money_source": "Card"})
        self.assertEqual(get_saved_expense_action(101).saved_expense.money_source, "Card")

    async def test_source_edit_retains_saved_amount_comment_and_cancel_preserves_record(self):
        action = create_saved_expense_action(101, saved())
        await expenses.saved_expense_action_handler(self.callback(f"exp:saved:source:{action.action_id}"))
        session = get_active_session(101)
        await self.choose(session, 1)
        args, kwargs = self.updates[0]
        self.assertEqual(args[1:], ("12", "comment"))
        self.assertEqual(kwargs, {"money_source": "Cash"})
        self.assertEqual(get_saved_expense_action(101).saved_expense.money_source, "Cash")
        await expenses.saved_expense_action_handler(self.callback(f"exp:saved:source:{action.action_id}"))
        session = get_active_session(101)
        await expenses.expense_cancel_handler(self.callback(f"exp:cancel:{session.session_id}"))
        self.assertEqual(get_saved_expense_action(101).saved_expense.money_source, "Cash")
        self.assertEqual(len(self.updates), 1)

    async def test_amount_edit_preserves_blank_historic_source(self):
        action = create_saved_expense_action(101, saved())
        session = create_session(101, "edit_saved_expense")
        session.saved_action_id = action.action_id
        await expenses._update_saved_expense(101, self.message, "20", "new")
        self.assertEqual(self.updates[0][1], {})
        self.assertEqual(self.source_reads, 0)
        self.assertIn("Не указан", self.message.answer.call_args.args[0])

    async def test_malformed_foreign_expired_and_inactive_choices_cannot_save(self):
        session = create_session(101, "choose_source")
        session.source_options = ("Inactive",)
        for data, user_id in [("exp:src", 101), (f"exp:src:{session.session_id}:0", 202),
                              ("exp:src:expired:0", 101), (f"exp:src:{session.session_id}:-1", 101),
                              (f"exp:src:{session.session_id}:999", 101)]:
            await expenses.expense_source_handler(self.callback(data, user_id))
        self.assertEqual(self.source_reads, 0)
        await self.choose(session)
        self.assertEqual(session.money_source, "")
        self.assertFalse(self.writes)
        self.assertFalse(self.updates)

    async def test_replaced_session_during_source_read_is_untouched(self):
        session = create_session(101, "choose_source")
        session.source_options = ("Cash",)
        async def replace_on_read(function, *args, **kwargs):
            create_session(101, "choose_category")
            await asyncio.sleep(0)
            return ["Cash"]
        with patch.object(expenses, "run_blocking", replace_on_read):
            await self.choose(session)
        self.assertEqual(get_active_session(101).state, "choose_category")
        self.assertFalse(self.writes)

    async def test_empty_sources_block_and_removed_source_rechecked_before_save(self):
        session = create_session(101, "enter_amount")
        session.amount = "12"
        session.money_source = "Removed"
        self.sources = []
        await expenses._finalize_expense(101, "user", self.message)
        self.assertEqual(session.state, "choose_source")
        self.assertFalse(self.writes)

    async def test_failed_source_read_and_expired_saved_action_do_not_persist(self):
        session = create_session(101, "choose_source")
        with patch.object(expenses, "run_blocking", AsyncMock(side_effect=RuntimeError("offline"))):
            await expenses._show_source_step(self.message, 101, session)
        self.assertEqual(session.source_options, ())
        self.assertIn("Источники", self.message.answer.call_args.args[0])
        action = create_saved_expense_action(101, saved())
        session = create_session(101, "choose_saved_source")
        session.saved_action_id = action.action_id
        session.source_options = ("Cash",)
        async def expire_action(function, *args, **kwargs):
            finalize_saved_expense_action(101)
            return ["Cash"]
        with patch.object(expenses, "run_blocking", expire_action):
            await self.choose(session)
        self.assertFalse(self.updates)

    async def test_source_edit_keyboard_is_optional_and_keeps_delete_cancel(self):
        keyboard = expenses._saved_edit_keyboard("action")
        callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
        self.assertEqual(callbacks, ["exp:saved:source:action", "exp:saved:delete:action", "exp:saved:cancel:action"])
        with patch.object(expenses, "TRACK_MONEY_SOURCE", False):
            keyboard = expenses._saved_edit_keyboard("action")
        self.assertEqual([b.callback_data for row in keyboard.inline_keyboard for b in row], callbacks[1:])
