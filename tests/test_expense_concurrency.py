import asyncio
from contextlib import ExitStack
from datetime import datetime, timezone
import unittest
from unittest.mock import AsyncMock, patch

import config  # Keep the runtime's stdlib-secrets import ordering.
from aiogram import Bot
from aiogram.types import CallbackQuery, Chat, Message, Update, User

import app
from handlers import expenses
from services.expenses import SavedExpense
from state.expense_session import create_session, get_active_session, pop_session
from state.saved_expense_actions import finalize_saved_expense_action


def message(user_id, chat_id, text="", message_id=1):
    return Message(
        message_id=message_id,
        date=datetime.now(timezone.utc),
        chat=Chat(id=chat_id, type="private"),
        from_user=User(id=user_id, is_bot=False, first_name="Test", username="test"),
        text=text,
    )


def subcategory_callback(session, user_id=101, chat_id=101):
    return CallbackQuery(
        id=f"sub-{user_id}",
        from_user=message(user_id, chat_id).from_user,
        chat_instance="test",
        message=message(user_id, chat_id),
        data=f"exp:sub:{session.session_id}:0",
    )


class ExpenseConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        for user_id in (101, 202):
            pop_session(user_id)
            finalize_saved_expense_action(user_id)

    async def test_amount_waits_for_subcategory_and_other_users_can_continue(self):
        dp = app.create_dispatcher()
        bot = Bot("123456:TEST_TOKEN")
        started, resume, amount_arrived = asyncio.Event(), asyncio.Event(), asyncio.Event()
        replies, writes, tasks = [], [], []

        async def answer(target, text, **kwargs):
            replies.append(text)
            return message(101, target.chat.id, text, len(replies) + 10)

        async def fake_run_blocking(fn, *args, **kwargs):
            if fn is expenses.get_subcategories_for_category:
                if args[0] == "Еда":
                    started.set()
                    await resume.wait()
                return ["Магазин"]
            if fn is expenses.is_allowed_username:
                return True, ""
            if fn is expenses.write_expense:
                writes.append(kwargs)
                return SavedExpense(
                    expense_id="test", sheet_name="Траты_по_месяцам", row_number=2,
                    row_range="A2:H2", date="2026-10-18", month_key="2026-10",
                    **kwargs,
                )
            raise AssertionError(f"Unexpected service call: {fn}")

        async def observe_update(handler, event, data):
            if event.message and event.message.text == "12,50 хлеб":
                amount_arrived.set()
            return await handler(event, data)

        # Observe arrival before the isolation middleware; routing must wait.
        dp.update.outer_middleware._middlewares.insert(0, observe_update)
        active = create_session(101, "choose_subcategory")
        active.category = "Еда"
        other = create_session(202, "choose_subcategory")
        other.category = "Транспорт"
        with ExitStack() as stack:
            stack.enter_context(patch.object(Message, "answer", answer))
            callback_answer = stack.enter_context(patch.object(CallbackQuery, "answer", new_callable=AsyncMock))
            stack.enter_context(patch.object(expenses, "check_access_callback", AsyncMock(return_value=True)))
            stack.enter_context(patch.object(expenses, "check_access_message", AsyncMock(return_value=True)))
            stack.enter_context(patch.object(expenses, "run_blocking", fake_run_blocking))
            stack.enter_context(patch.object(expenses, "_safe_delete_prompt", AsyncMock()))
            stack.enter_context(patch.object(expenses, "_show_category_card", AsyncMock()))
            try:
                tasks.append(asyncio.create_task(dp.feed_update(bot, Update(
                    update_id=1, callback_query=subcategory_callback(active)))))
                await asyncio.wait_for(started.wait(), 2)
                # Same user in another chat: sessions are global per user.
                tasks.append(asyncio.create_task(dp.feed_update(bot, Update(
                    update_id=2, message=message(101, 303, "12,50 хлеб")))))
                await asyncio.wait_for(amount_arrived.wait(), 2)
                self.assertFalse(tasks[-1].done())
                # A different user must not wait for the first user's Sheets read.
                await asyncio.wait_for(dp.feed_update(bot, Update(
                    update_id=3, callback_query=subcategory_callback(other, 202, 202))), 2)
                self.assertEqual(get_active_session(202).state, "enter_amount")
                resume.set()
                await asyncio.wait_for(asyncio.gather(*tasks), 2)
                self.assertEqual(len(writes), 1)
                self.assertEqual(writes[0]["amount"], "12,50")
                self.assertEqual(writes[0]["comment"], "хлеб")
                self.assertTrue(any("Введите сумму" in text for text in replies))
                self.assertTrue(any("Трата добавлена" in text for text in replies))
                self.assertFalse(any("устарел" in text for text in replies))
                self.assertFalse(any("устарел" in str(call) for call in callback_answer.call_args_list))
                self.assertIsNone(get_active_session(101))
            finally:
                resume.set()
                await asyncio.gather(*tasks, return_exceptions=True)
                await dp.fsm.close()
                await bot.session.close()

    async def test_removed_or_replaced_session_does_not_show_amount_prompt(self):
        for replace in (False, True):
            with self.subTest(replace=replace):
                active = create_session(101, "choose_subcategory")
                active.category = "Еда"
                callback = subcategory_callback(active)
                replacement = None

                async def read_subcategories(*args):
                    nonlocal replacement
                    if replace:
                        replacement = create_session(101, "choose_category")
                    else:
                        pop_session(101)
                    return ["Магазин"]

                with (
                    patch.object(expenses, "check_access_callback", AsyncMock(return_value=True)),
                    patch.object(expenses, "run_blocking", read_subcategories),
                    patch.object(expenses, "_safe_delete_prompt", AsyncMock()),
                    patch.object(Message, "answer", new_callable=AsyncMock) as answer,
                    patch.object(CallbackQuery, "answer", new_callable=AsyncMock) as alert,
                ):
                    await expenses.expense_subcategory_handler(callback)
                    answer.assert_not_awaited()
                    alert.assert_awaited_once_with("Шаг устарел, начните заново", show_alert=True)
                    self.assertIs(get_active_session(101), replacement)
                    self.assertEqual(active.state, "choose_subcategory")


if __name__ == "__main__":
    unittest.main()
