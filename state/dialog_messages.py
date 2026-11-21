"""One temporary Telegram message (or active result keyboard) per user."""
import logging
from contextvars import ContextVar
from dataclasses import dataclass
from time import monotonic

from aiogram import BaseMiddleware, Bot, types
from aiogram.exceptions import TelegramAPIError

STEP_TIMEOUT = 900


@dataclass(frozen=True)
class DialogMessage:
    chat_id: int
    message_id: int
    text: str
    base_text: str
    markup: types.InlineKeyboardMarkup | types.ReplyKeyboardMarkup | None
    expires_at: float
    keep: bool
    retained_markup: types.InlineKeyboardMarkup | None


@dataclass
class Dialog:
    bot: Bot
    messages: dict[tuple[int, int], DialogMessage]
    key: tuple[int, int]
    callback_message: types.Message | types.InaccessibleMessage | None

    @property
    def current(self) -> DialogMessage | None:
        return self.messages.get(self.key)

    async def close(self) -> None:
        previous = self.messages.pop(self.key, None)
        if previous is None:
            return
        if not previous.keep:
            try:
                await self.bot.delete_message(chat_id=previous.chat_id, message_id=previous.message_id)
                return
            except TelegramAPIError:
                logging.debug("Не удалось удалить сообщение диалога", exc_info=True)
        if isinstance(previous.markup, types.InlineKeyboardMarkup):
            try:
                await self.bot.edit_message_reply_markup(
                    chat_id=previous.chat_id, message_id=previous.message_id,
                    reply_markup=previous.retained_markup,
                )
            except TelegramAPIError:
                logging.debug("Не удалось свернуть кнопки диалога", exc_info=True)

    async def show(self, target, text, markup, *, keep=False, retained_markup=None, ttl=STEP_TIMEOUT, base_text=None):
        previous = self.current
        inline = markup is None or isinstance(markup, types.InlineKeyboardMarkup)
        if (self.callback_message and previous and not previous.keep and inline
                and self.callback_message.chat.id == target.chat.id == previous.chat_id
                and self.callback_message.message_id == previous.message_id):
            try:
                if text != previous.text or markup != previous.markup:
                    await self.bot.edit_message_text(
                        chat_id=previous.chat_id, message_id=previous.message_id,
                        text=text, reply_markup=markup,
                    )
                message_id = previous.message_id
            except TelegramAPIError:
                logging.debug("Не удалось обновить сообщение диалога", exc_info=True)
                previous = None
        else:
            previous = None

        if previous is None:
            sent = await target.answer(text, reply_markup=markup)
            message_id = sent.message_id
            await self.close()

        if keep and (not isinstance(markup, types.InlineKeyboardMarkup) or markup == retained_markup):
            self.messages.pop(self.key, None)
            return
        self.messages[self.key] = DialogMessage(
            target.chat.id, message_id, text, text if base_text is None else base_text, markup, monotonic() + ttl, keep, retained_markup,
        )


_current_dialog: ContextVar[Dialog | None] = ContextVar("current_dialog", default=None)


class DialogMessagesMiddleware(BaseMiddleware):
    def __init__(self):
        self.messages: dict[tuple[int, int], DialogMessage] = {}

    async def __call__(self, handler, event, data):
        user = event.from_user
        if user is None:
            return await handler(event, data)
        bot = data["bot"]
        callback_message = event.message if isinstance(event, types.CallbackQuery) else None
        dialog = Dialog(bot, self.messages, (bot.id, user.id), callback_message)
        token = _current_dialog.set(dialog)
        try:
            current = dialog.current
            if current and current.expires_at <= monotonic():
                await dialog.close()
            return await handler(event, data)
        finally:
            _current_dialog.reset(token)


async def dialog_step(target, text, *, reply_markup=None):
    dialog = _current_dialog.get()
    if dialog is None:
        return await target.answer(text, reply_markup=reply_markup)
    await dialog.show(target, text, reply_markup)


async def dialog_hint(target, text):
    """Replace a validation prompt while keeping its current actions."""
    dialog = _current_dialog.get()
    current = dialog.current if dialog else None
    if current and current.chat_id == target.chat.id:
        # Keep retry actions available, without repeating a retained receipt.
        base = current.base_text if not current.keep else ""
        hint = f"{text}\n\n{base}" if base else text
        await dialog.show(target, hint, current.markup, base_text=base)
    else:
        await dialog_step(target, text)


async def dialog_result(target, text, *, reply_markup=None, retained_markup=None, ttl=STEP_TIMEOUT):
    dialog = _current_dialog.get()
    if dialog is None:
        return await target.answer(text, reply_markup=reply_markup)
    await dialog.show(target, text, reply_markup, keep=True, retained_markup=retained_markup, ttl=ttl)


async def close_dialog():
    dialog = _current_dialog.get()
    if dialog:
        await dialog.close()


def is_current_action(target, action, *, shared=False) -> bool:
    dialog = _current_dialog.get()
    if dialog is None:
        return True  # Handlers can also be invoked directly.
    messages = dialog.messages.values() if shared and target.chat.type != "private" else [dialog.current]
    return any(
        message and message.chat_id == target.chat.id and message.message_id == target.message_id
        and isinstance(message.markup, types.InlineKeyboardMarkup)
        and any(button.callback_data == action for row in message.markup.inline_keyboard for button in row)
        for message in messages
    )
