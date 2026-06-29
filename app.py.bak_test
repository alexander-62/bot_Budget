import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN
from handlers.expenses import router as expenses_router
from handlers.menu import router as menu_router
from handlers.shopping import router as shopping_router
from services.access import get_allowed_chat_ids


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    logging.getLogger("aiogram.dispatcher").setLevel(logging.WARNING)
    logging.getLogger("root").setLevel(logging.INFO)


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(shopping_router)
    dp.include_router(expenses_router)
    dp.include_router(menu_router)
    return dp


async def notify_startup(bot: Bot) -> None:
    try:
        chat_ids = get_allowed_chat_ids()
    except Exception:
        logging.exception("Не удалось загрузить chat_id пользователей для стартовой рассылки")
        return

    if not chat_ids:
        logging.info("Стартовая рассылка пропущена: в Users нет chat_id/user_id")
        return

    sent = 0
    for chat_id in chat_ids:
        try:
            await bot.send_message(chat_id=chat_id, text="Бот запущен")
            sent += 1
        except Exception:
            logging.exception("Не удалось отправить стартовое сообщение в chat_id=%s", chat_id)

    logging.info("Стартовая рассылка завершена: отправлено %s из %s", sent, len(chat_ids))


async def main() -> None:
    setup_logging()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = create_dispatcher()
    logging.info("Бот запущен...")
    await notify_startup(bot)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Бот остановлен")
