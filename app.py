import asyncio
import json
import logging
from pathlib import Path

# Import config before aiogram so local secrets.py cannot shadow stdlib secrets.
from config import BOT_TOKEN, WEBAPP_HOST, WEBAPP_PORT
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from handlers.expenses import router as expenses_router
from handlers.menu import router as menu_router
from handlers.shopping import router as shopping_router
from scheduler import run_daily_digest_scheduler
from services.async_tools import run_blocking
from services.access import get_allowed_chat_ids
from services.startup_validation import StartupValidationError, validate_startup
from version import __version__

RESTART_NOTICE_FILE = Path(__file__).resolve().parent / ".restart_notice.json"


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


def create_web_app() -> web.Application:
    base_dir = Path(__file__).resolve().parent
    webapp_dir = base_dir / "webapp"
    static_dir = webapp_dir / "static"

    app = web.Application()

    async def webapp_index(_: web.Request) -> web.FileResponse:
        return web.FileResponse(webapp_dir / "index.html")

    async def webapp_health(_: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    app.router.add_get("/webapp", webapp_index)
    app.router.add_get("/webapp/health", webapp_health)
    app.router.add_static("/webapp/static/", path=static_dir)
    return app


async def start_web_server() -> web.AppRunner:
    app = create_web_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=WEBAPP_HOST, port=WEBAPP_PORT)
    try:
        await site.start()
    except OSError as exc:
        await runner.cleanup()
        raise RuntimeError(
            f"Web App port {WEBAPP_HOST}:{WEBAPP_PORT} is unavailable. Stop old bot process or free port."
        ) from exc
    logging.info("Web App server started at http://%s:%s/webapp", WEBAPP_HOST, WEBAPP_PORT)
    return runner


async def notify_startup(bot: Bot) -> None:
    try:
        chat_ids = await run_blocking(get_allowed_chat_ids)
    except Exception:
        logging.exception("Не удалось загрузить chat_id пользователей для стартовой рассылки")
        return

    if not chat_ids:
        logging.info("Стартовая рассылка пропущена: в Users нет chat_id/user_id")
        return

    sent = 0
    for chat_id in chat_ids:
        try:
            await bot.send_message(chat_id=chat_id, text=f"Бот запущен. Версия: {__version__}")
            sent += 1
        except Exception:
            logging.exception("Не удалось отправить стартовое сообщение в chat_id=%s", chat_id)

    logging.info("Стартовая рассылка завершена: отправлено %s из %s", sent, len(chat_ids))


async def notify_restart_complete(bot: Bot) -> None:
    if not RESTART_NOTICE_FILE.exists():
        return

    try:
        notice = json.loads(RESTART_NOTICE_FILE.read_text(encoding="utf-8"))
    except Exception:
        logging.exception("Не удалось прочитать marker перезапуска")
        try:
            RESTART_NOTICE_FILE.unlink()
        except Exception:
            logging.exception("Не удалось удалить поврежденный marker перезапуска")
        return

    chat_id = notice.get("chat_id")
    if not isinstance(chat_id, int):
        logging.warning("Marker перезапуска не содержит корректный chat_id")
        try:
            RESTART_NOTICE_FILE.unlink()
        except Exception:
            logging.exception("Не удалось удалить marker перезапуска")
        return

    try:
        await bot.send_message(chat_id=chat_id, text=f"Бот снова запущен. Версия: {__version__}")
    except Exception:
        logging.exception("Не удалось отправить сообщение о завершении перезапуска chat_id=%s", chat_id)
        return

    try:
        RESTART_NOTICE_FILE.unlink()
    except Exception:
        logging.exception("Не удалось удалить marker перезапуска после отправки")


async def main() -> None:
    setup_logging()
    try:
        await run_blocking(validate_startup)
    except StartupValidationError as exc:
        logging.error("Startup validation failed: %s", exc)
        return

    web_runner = await start_web_server()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = create_dispatcher()
    logging.info("Бот запущен. Версия: %s", __version__)
    digest_task = asyncio.create_task(run_daily_digest_scheduler(bot))
    try:
        await notify_startup(bot)
        await notify_restart_complete(bot)
        await dp.start_polling(bot)
    finally:
        digest_task.cancel()
        try:
            await digest_task
        except asyncio.CancelledError:
            pass
        await web_runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Бот остановлен")
