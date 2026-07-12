# External Integrations

**Analysis Date:** 2026-06-29

## APIs & External Services

**Telegram Bot API:**
- Telegram Bot API - Handles bot commands, messages, callback queries, keyboards, and startup notifications.
  - SDK/Client: `aiogram` from `requirements.txt`.
  - Auth: `BOT_TOKEN` exposed by `config.py` from ignored `.env` or environment variables.
  - Entry point: `app.py` creates `Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))`.
  - Update delivery: `app.py` uses `Dispatcher.start_polling(bot)`; no Telegram webhook endpoint is registered.
  - Routers: `handlers/menu.py`, `handlers/expenses.py`, and `handlers/shopping.py` are included by `create_dispatcher()` in `app.py`.

**Telegram Web Apps:**
- Telegram Web App JavaScript SDK - Lets the static web page run inside Telegram clients.
  - SDK/Client: `https://telegram.org/js/telegram-web-app.js` loaded by `webapp/index.html`.
  - Auth: Telegram Web App context is accessed client-side through `window.Telegram.WebApp`; no server-side init data verification detected.
  - Bot button: `keyboards/main.py` creates `KeyboardButton(..., web_app=WebAppInfo(url=WEBAPP_URL))`.
  - URL config: `WEBAPP_URL` exposed by `config.py` from ignored `.env` or environment variables, defaulting to the configured local web app URL when missing.

**Google Sheets API:**
- Google Sheets - Primary data store for allowed users, budget categories, limits, expenses, and shopping list items.
  - SDK/Client: `gspread` from `requirements.txt`.
  - Auth: `GOOGLE_CREDENTIALS_FILE` exposed by `config.py` from ignored `.env` or environment variables.
  - Spreadsheet selection: `SPREADSHEET_ID` exposed by `config.py` from ignored `.env` or environment variables.
  - Client factory: `services/google_sheets.py` calls `gspread.service_account(filename=str(get_credentials_path()))` and `gc.open_by_key(SPREADSHEET_ID)`.
  - Setup docs: `GOOGLE_SETUP.md` documents enabling Google Sheets API and Google Drive API, creating a service account JSON key, and sharing the spreadsheet with the service account.

**Google Drive API:**
- Google Drive API - Required by the Google service account setup for spreadsheet file access.
  - SDK/Client: accessed indirectly through `gspread`/Google client dependencies.
  - Auth: same service account JSON referenced by `GOOGLE_CREDENTIALS_FILE`.
  - Setup docs: `GOOGLE_SETUP.md` instructs enabling Google Drive API alongside Google Sheets API.

**Local HTTP Web App:**
- aiohttp local web server - Serves the Telegram Web App page and static assets.
  - SDK/Client: `aiohttp.web` imported directly in `app.py`.
  - Auth: none.
  - Routes: `/webapp`, `/webapp/health`, and `/webapp/static/` in `app.py`.
  - Bind config: `WEBAPP_HOST` and `WEBAPP_PORT` from `config.py`.

## Data Storage

**Databases:**
- Google Sheets
  - Connection: `SPREADSHEET_ID` and `GOOGLE_CREDENTIALS_FILE`.
  - Client: `gspread`.
  - Access helper: `services/google_sheets.py`.
  - Worksheets: names are centralized in `constants.py` as `USERS_SHEET_NAME`, `CATEGORIES_SHEET_NAME`, `LIMITS_SHEET_NAME`, `EXPENSES_SHEET_NAME`, and `SHOPPING_SHEET_NAME`.
  - User access data: `services/access.py` reads and updates the users worksheet.
  - Budget limits and spend summaries: `services/budget.py` reads categories, limits, and expenses worksheets.
  - Expense writes: `services/expenses.py` writes rows to the expenses worksheet.
  - Shopping list writes: `services/shopping.py` reads, updates, deletes rows, and clears the shopping worksheet.

**File Storage:**
- Local filesystem only.
- Static assets: `webapp/static/logo.png` served by `app.py`.
- Local runtime files: `.bot.pid` and `bot.log` managed by `manage_bot.py` and ignored by `.gitignore`.
- Secret/config files: `.env` and `credentials.json` are ignored by `.gitignore` and must not be read for documentation.

**Caching:**
- In-memory access caches in `services/access.py`.
- Cache TTL is configured by `ACCESS_CACHE_TTL_SECONDS` in `constants.py`.
- Cached values include allowed usernames, allowed chat IDs, and username-to-chat-ID mappings.
- No external cache service detected.

## Authentication & Identity

**Auth Provider:**
- Telegram identity plus Google Sheets allowlist.
  - Implementation: `services/access.py` checks `message.from_user.username` or `callback.from_user.username` against the `Users` worksheet.
  - Chat ID synchronization: `services/access.py` writes Telegram user IDs back to the users worksheet when usernames match.
  - Failure behavior: handler access checks in `handlers/menu.py`, `handlers/expenses.py`, and `handlers/shopping.py` deny missing usernames and usernames absent from Google Sheets.

**Service Authentication:**
- Telegram bot token is read as `BOT_TOKEN` through `config.py`.
- Google service account credentials are read from the file path named by `GOOGLE_CREDENTIALS_FILE`.
- Spreadsheet ID is read as `SPREADSHEET_ID` through `config.py`.

## Monitoring & Observability

**Error Tracking:**
- None detected.

**Logs:**
- Python standard `logging`.
- `app.py` configures log format, log level, and lowers noisy `aiogram` logger levels.
- `manage_bot.py` redirects background process stdout and stderr to `bot.log`.
- Handlers and services use `logging.exception()`, `logging.warning()`, and `logging.info()` around Google Sheets access, shopping actions, expense writes, startup notification, and restart actions.

## CI/CD & Deployment

**Hosting:**
- Not detected.
- Runtime is local/process based through `bot.py`, `manage_bot.py`, and the unified `bot.bat` launcher.

**CI Pipeline:**
- None detected.
- No `.github/workflows/`, GitLab CI, or equivalent pipeline config detected.

## Environment Configuration

**Required env vars:**
- Not applicable. The code does not read environment variables for application configuration.

**Required config names:**
- `BOT_TOKEN` in ignored `.env` or environment variables.
- `GOOGLE_CREDENTIALS_FILE` in ignored `.env` or environment variables.
- `SPREADSHEET_ID` in ignored `.env` or environment variables.
- Optional `WEBAPP_URL` in ignored `.env` or environment variables.
- Optional `WEBAPP_HOST` in ignored `.env` or environment variables.
- Optional `WEBAPP_PORT` in ignored `.env` or environment variables.

**Secrets location:**
- `.env` for application config and token names.
- `credentials.json` or the file path named by `GOOGLE_CREDENTIALS_FILE` for Google service account JSON.
- `.gitignore` excludes `secrets.py`, `.env`, `*.env`, and `credentials.json`.

## Webhooks & Callbacks

**Incoming:**
- Telegram webhook: None. `app.py` uses long polling.
- HTTP routes: `/webapp`, `/webapp/health`, and `/webapp/static/` are served by `aiohttp` in `app.py`.
- Bot callback query handlers: `handlers/menu.py`, `handlers/expenses.py`, and `handlers/shopping.py` process inline keyboard callback data inside Telegram updates.

**Outgoing:**
- Telegram Bot API calls through `aiogram`, including `send_message`, `answer`, `delete_message`, and callback responses across `app.py` and `handlers/`.
- Google Sheets API calls through `gspread`, including `worksheets()`, `col_values()`, `get_all_values()`, `update_cell()`, `update()`, `delete_rows()`, and `batch_clear()` in `services/`.
- Google Sheets direct link generated by `services/google_sheets.py` as `https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit` without exposing the configured spreadsheet ID in committed docs.

---

*Integration audit: 2026-06-29*
