# Bot Budget

Telegram-бот для учета бюджета с Google Sheets.

## Запуск

### Обычный запуск (в текущей консоли)

```bash
python bot.py
```

Остановка: `Ctrl+C` (без длинного traceback).

### Управление из консоли (старт/стоп/рестарт)

```bash
python manage_bot.py start
python manage_bot.py status
python manage_bot.py stop
python manage_bot.py restart
```

- `start` запускает бота в фоне.
- Логи фонового процесса пишутся в `bot.log`.

Если нужен запуск в текущей консоли через менеджер:

```bash
python manage_bot.py start --foreground
```

## Логи

- Шумные технические логи `aiogram` приглушены.
- Остаются ключевые сообщения приложения и ошибки.

