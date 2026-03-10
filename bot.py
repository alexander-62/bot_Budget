from app import main

if __name__ == "__main__":
    import asyncio
    import logging

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Бот остановлен")
