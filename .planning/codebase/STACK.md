# Technology Stack

**Analysis Date:** 2026-06-29

## Languages

**Primary:**
- Python 3.14.5 - Telegram bot runtime, Google Sheets service layer, local process manager, and integration test scripts in `app.py`, `bot.py`, `manage_bot.py`, `services/`, `handlers/`, `keyboards/`, `state/`, and `test_google.py`.

**Secondary:**
- HTML/CSS/JavaScript - Telegram Web App page in `webapp/index.html`.
- Windows Batch - Local launcher wrappers in `start_bot.bat` and `restart_bot.bat`.
- Markdown - Project docs in `README.md`, `GOOGLE_SETUP.md`, `BOT_TZ.md`, and `BOT_TZ (2).md`.

## Runtime

**Environment:**
- CPython 3.14.5 detected from `python --version`.
- Asyncio event loop drives both the bot and local web server from `app.py`.
- Current global interpreter does not have declared packages installed: importing `aiogram`, `gspread`, or `aiohttp` fails in the inspected environment.

**Package Manager:**
- pip 26.1.1 detected from `python -m pip --version`.
- Dependencies are declared in `requirements.txt`.
- Lockfile: missing. There is no `requirements.lock`, `poetry.lock`, `Pipfile.lock`, or equivalent pinned dependency lockfile.

## Frameworks

**Core:**
- aiogram >=3.0.0 - Telegram Bot API framework used by `app.py`, `handlers/menu.py`, `handlers/expenses.py`, `handlers/shopping.py`, and keyboard modules under `keyboards/`.
- aiohttp version not pinned - Local HTTP server used directly in `app.py` for `/webapp`, `/webapp/health`, and static assets under `/webapp/static/`. It is imported by source but not declared directly in `requirements.txt`.
- gspread version not pinned - Google Sheets client used by `services/google_sheets.py`, `services/access.py`, `services/budget.py`, `services/expenses.py`, `services/shopping.py`, and `test_google.py`.

**Testing:**
- No dedicated test framework detected.
- `test_google.py` is a manual Google Sheets connectivity script using `gspread`.

**Build/Dev:**
- No build system detected.
- `.editorconfig` sets UTF-8, LF endings, and final newline.
- `.vscode/settings.json` sets UTF-8 behavior and Windows terminal environment variables `PYTHONUTF8` and `PYTHONIOENCODING`.
- `manage_bot.py` provides local start, stop, restart, and status commands using `subprocess`, `.bot.pid`, and `bot.log`.
- `start_bot.bat` and `restart_bot.bat` prefer `.venv\Scripts\python.exe` when present and fall back to `python`.

## Key Dependencies

**Critical:**
- aiogram >=3.0.0 - Owns Telegram long polling, message handlers, callback handlers, reply keyboards, inline keyboards, and Telegram Web App button support.
- gspread unpinned - Owns all persistence and configuration-backed business data through Google Sheets.
- aiohttp unpinned / undeclared - Serves the local Web App routes created in `app.py`; add it explicitly to `requirements.txt` if relying on it outside aiogram transitive dependencies.

**Infrastructure:**
- Python standard library `asyncio` - Runs `main()` in `app.py` and `bot.py`.
- Python standard library `logging` - Configured in `app.py` and used across `handlers/` and `services/`.
- Python standard library `subprocess`, `os`, `signal`, `sys`, and `pathlib` - Used by `manage_bot.py` for process management.
- Python standard library `dataclasses`, `datetime`, and `decimal` - Used by `services/budget.py`, `services/expenses.py`, and session modules for data modeling and money parsing.

## Configuration

**Environment:**
- Configuration is `.env`/environment-variable based.
- `config.py` loads `.env` and exposes `BOT_TOKEN`, `GOOGLE_CREDENTIALS_FILE`, `SPREADSHEET_ID`, `WEBAPP_URL`, `WEBAPP_HOST`, and `WEBAPP_PORT`.
- `.env` is ignored by git and is expected to provide secret/config values.
- `credentials.json` is ignored by git and is expected to contain Google service account credentials referenced by `GOOGLE_CREDENTIALS_FILE`.
- `.env.example` documents the required local config names without real values.

**Build:**
- `requirements.txt`: declares Python runtime dependencies.
- `.editorconfig`: editor formatting defaults.
- `.vscode/settings.json`: local VS Code encoding and terminal environment settings.
- `.gitignore`: excludes `secrets.py`, `.env`, `*.env`, `credentials.json`, `.bot.pid`, `bot.log`, virtualenvs, Python caches, and IDE files.
- No `pyproject.toml`, `setup.py`, `setup.cfg`, Dockerfile, compose file, or CI config detected.

## Platform Requirements

**Development:**
- Python with pip.
- Install dependencies with `pip install -r requirements.txt`.
- Create local `.env` with `BOT_TOKEN`, `GOOGLE_CREDENTIALS_FILE`, `SPREADSHEET_ID`, and optional `WEBAPP_URL`, `WEBAPP_HOST`, `WEBAPP_PORT`.
- Place Google service account JSON at the path configured by `GOOGLE_CREDENTIALS_FILE`.
- Google Sheets API and Google Drive API must be enabled for the service account project, as documented in `GOOGLE_SETUP.md`.
- Share the target spreadsheet with the Google service account email with editor access.

**Production:**
- Deployment target is not formalized.
- Current runtime model is a long-running Python process started by `python bot.py`, `python manage_bot.py start`, `start_bot.bat`, or `restart_bot.bat`.
- Telegram updates use long polling via `Dispatcher.start_polling()` in `app.py`; no webhook deployment is configured.
- The Web App server binds to `WEBAPP_HOST` and `WEBAPP_PORT` from `config.py` and serves local assets from `webapp/`.

---

*Stack analysis: 2026-06-29*
