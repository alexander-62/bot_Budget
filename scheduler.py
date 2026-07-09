from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from constants import DAILY_DIGEST_CHECK_INTERVAL_SECONDS
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
        try:
            await send_due_daily_digests(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("Не удалось выполнить проверку вечерней рассылки")

        await asyncio.sleep(DAILY_DIGEST_CHECK_INTERVAL_SECONDS)


async def send_due_daily_digests(bot: Bot) -> int:
    if not await run_blocking(is_digest_due):
        return 0

    digest_date = await run_blocking(get_current_digest_date)
    recipients = await run_blocking(get_digest_recipients)
    due_recipients = [recipient for recipient in recipients if recipient.last_digest_date != digest_date.isoformat()]
    if not due_recipients:
        return 0

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
