from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from constants import DAILY_DIGEST_CHECK_INTERVAL_SECONDS
from config import PLANNED_EXPENSES_ENABLED
from services.async_tools import run_blocking
from services.daily_digest import (
    build_daily_digest_summary,
    format_daily_digest_message,
    get_current_digest_date,
    get_digest_recipients,
    is_digest_due,
    mark_digest_sent,
)


async def run_daily_digest_scheduler(bot: Bot) -> None:
    while True:
        for send in (send_due_daily_digests, send_due_planned_reminders):
            try:
                await send(bot)
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.exception("Не удалось выполнить проверку рассылки %s", send.__name__)

        await asyncio.sleep(DAILY_DIGEST_CHECK_INTERVAL_SECONDS)


async def send_due_daily_digests(bot: Bot) -> int:
    if not await run_blocking(is_digest_due):
        return 0

    digest_date = await run_blocking(get_current_digest_date)
    recipients = await run_blocking(get_digest_recipients)
    due_recipients = [recipient for recipient in recipients if recipient.last_digest_date != digest_date.isoformat()]
    if not due_recipients:
        return 0

    from services.budget_settings import settings_initialized, refresh_runtime_settings
    if settings_initialized():
        await run_blocking(refresh_runtime_settings)
    summary = await run_blocking(build_daily_digest_summary, digest_date)
    message_text = format_daily_digest_message(summary)

    sent = 0
    for recipient in due_recipients:
        try:
            await bot.send_message(chat_id=recipient.chat_id, text=message_text)
            await run_blocking(mark_digest_sent, recipient.row_number, digest_date)
            sent += 1
        except Exception:
            logging.exception(
                "Не удалось отправить вечернюю рассылку username=%s chat_id=%s",
                recipient.username,
                recipient.chat_id,
            )

    logging.info(
        "Вечерняя рассылка за %s: отправлено %s из %s",
        digest_date.isoformat(),
        sent,
        len(due_recipients),
    )
    return sent


async def send_due_planned_reminders(bot: Bot) -> int:
    if not PLANNED_EXPENSES_ENABLED:
        return 0
    from services.planned_reminders import build_reminder_jobs, mark_delivered
    from services.budget_settings import settings_initialized, refresh_runtime_settings
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    if settings_initialized():
        await run_blocking(refresh_runtime_settings)
    jobs = await run_blocking(build_reminder_jobs)
    sent = 0
    for job in jobs:
        markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=title[:60], callback_data=f"fut:open:{item[0]}"),
            InlineKeyboardButton(text="Напомнить позже", callback_data=f"fut:snooze:{item[0]}")
        ] for item, title in zip(job.items, job.titles)])
        try:
            await bot.send_message(chat_id=job.chat_id, text=job.text, reply_markup=markup)
            await run_blocking(mark_delivered, job)
            sent += 1
        except Exception:
            logging.exception("Не удалось отправить напоминание о будущем платеже chat_id=%s", job.chat_id)
    return sent
