# Codebase Structure

**Analysis Date:** 2026-06-29

## Directory Layout

```text
bot_Budget/
├── app.py                    # Main async application bootstrap
├── bot.py                    # Minimal bot entry point
├── manage_bot.py             # Start/stop/restart/status process manager
├── config.py                 # Secret-backed runtime config names
├── constants.py              # Sheet names, callbacks, TTLs, UI constants
├── requirements.txt          # Python dependency list
├── README.md                 # Runtime commands and logging notes
├── GOOGLE_SETUP.md           # Google Sheets/service-account setup notes
├── BOT_TZ.md                 # Project/domain notes
├── handlers/                 # aiogram router modules by feature
├── keyboards/                # aiogram keyboard builder modules
├── services/                 # Domain services and Google Sheets adapter
├── state/                    # In-memory conversation sessions
├── webapp/                   # Static Telegram Web App assets
├── .planning/codebase/       # Generated codebase map documents
├── .vscode/                  # Local editor settings
├── start_bot.bat             # Windows foreground start wrapper
└── restart_bot.bat           # Windows restart wrapper
```

## Directory Purposes

**Repository root:**
- Purpose: Runtime entry points, configuration, documentation, local scripts, and ignored runtime artifacts.
- Contains: `app.py`, `bot.py`, `manage_bot.py`, `config.py`, `constants.py`, `requirements.txt`, `README.md`, `GOOGLE_SETUP.md`, `start_bot.bat`, `restart_bot.bat`.
- Key files: `app.py`, `bot.py`, `manage_bot.py`, `config.py`, `constants.py`.

**`handlers/`:**
- Purpose: aiogram router modules that receive Telegram messages/callback queries and orchestrate services, sessions, and keyboards.
- Contains: `handlers/menu.py`, `handlers/expenses.py`, `handlers/shopping.py`, `handlers/__init__.py`, plus duplicate file `handlers/expenses (2).py`.
- Key files: `handlers/menu.py`, `handlers/expenses.py`, `handlers/shopping.py`.

**`keyboards/`:**
- Purpose: Centralized builders for reply keyboards and inline keyboards.
- Contains: `keyboards/main.py`, `keyboards/limits.py`, `keyboards/expenses.py`, `keyboards/shopping.py`, `keyboards/__init__.py`, plus backup/temp artifacts.
- Key files: `keyboards/main.py`, `keyboards/expenses.py`, `keyboards/shopping.py`, `keyboards/limits.py`.

**`services/`:**
- Purpose: Domain behavior and Google Sheets persistence interactions.
- Contains: `services/access.py`, `services/budget.py`, `services/expenses.py`, `services/shopping.py`, `services/google_sheets.py`, `services/__init__.py`, plus duplicate file `services/expenses (2).py`.
- Key files: `services/google_sheets.py`, `services/access.py`, `services/budget.py`, `services/expenses.py`, `services/shopping.py`.

**`state/`:**
- Purpose: Process-local state for multi-step Telegram conversations.
- Contains: `state/expense_session.py`, `state/shopping_session.py`, `state/__init__.py`.
- Key files: `state/expense_session.py`, `state/shopping_session.py`.

**`webapp/`:**
- Purpose: Static Telegram Web App page served by aiohttp from `app.py`.
- Contains: `webapp/index.html`, `webapp/static/logo.png`.
- Key files: `webapp/index.html`, `webapp/static/logo.png`.

**`.planning/codebase/`:**
- Purpose: Generated codebase intelligence for GSD planning/execution commands.
- Contains: `ARCHITECTURE.md`, `STRUCTURE.md`.
- Key files: `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/STRUCTURE.md`.

## Key File Locations

**Entry Points:**
- `bot.py`: Minimal runtime entry point for `python bot.py`; imports and runs `app.main`.
- `app.py`: Main async application setup, dispatcher creation, Web App server, bot polling.
- `manage_bot.py`: CLI process lifecycle manager for `start`, `stop`, `restart`, and `status`.
- `start_bot.bat`: Windows wrapper that runs `manage_bot.py start --foreground`, preferring `.venv\Scripts\python.exe`.
- `restart_bot.bat`: Windows wrapper that runs `manage_bot.py restart`, preferring `.venv\Scripts\python.exe`.
- `test_google.py`: Manual Google Sheets connectivity/write probe.

**Configuration:**
- `config.py`: Imports `BOT_TOKEN`, `GOOGLE_CREDENTIALS_FILE`, and `SPREADSHEET_ID` from `secrets.py`; provides defaults for `WEBAPP_URL`, `WEBAPP_HOST`, and `WEBAPP_PORT`.
- `constants.py`: Defines worksheet names, menu/callback constants, session TTLs, access cache TTL, and shopping item max length.
- `.gitignore`: Ignores `secrets.py`, `.env`, `credentials.json`, `.bot.pid`, `bot.log`, virtualenv folders, caches, and editor files.
- `.editorconfig`: Requires UTF-8, LF endings, and final newlines.
- `requirements.txt`: Lists runtime dependencies `aiogram>=3.0.0` and `gspread`.

**Core Logic:**
- `handlers/menu.py`: Main menu, limit display, recent expenses display, category details, restart command, fallback.
- `handlers/expenses.py`: Add-expense state machine and expense finalization.
- `handlers/shopping.py`: Shopping list state machine and item mutations.
- `services/access.py`: Google Sheets-backed username authorization and chat id sync.
- `services/budget.py`: Budget/category/month aggregations.
- `services/expenses.py`: Amount parsing, expense append, recent expense reads.
- `services/shopping.py`: Shopping list reads/writes/deletes/clear.
- `services/google_sheets.py`: gspread client and worksheet adapter.
- `state/expense_session.py`: Expense session dataclass and session store.
- `state/shopping_session.py`: Shopping session dataclass and session store.

**UI Construction:**
- `keyboards/main.py`: Main reply keyboard and Telegram Web App button.
- `keyboards/limits.py`: Category list and category action inline keyboards.
- `keyboards/expenses.py`: Expense flow category/subcategory/cancel/confirm inline keyboards.
- `keyboards/shopping.py`: Shopping action/cancel/clear-confirm inline keyboards.
- `webapp/index.html`: Static Web App HTML/CSS/JS.

**Testing and Probes:**
- `test_google.py`: Manual probe, not a unit test suite.
- `example.py`: Empty placeholder file.
- `app.py.bak_test`, `keyboards/main.py.bak_test`, `handlers/expenses (2).py`, `services/expenses (2).py`: Backup/duplicate artifacts; do not use as primary implementation targets.

**Secrets and Runtime Artifacts:**
- `secrets.py`: Secret-bearing Python config module; reference variable names only.
- `credentials.json`: Secret-bearing Google service account file; do not read or quote.
- `.bot.pid`: Runtime PID file used by `manage_bot.py`.
- `bot.log`: Runtime log file used by `manage_bot.py`.

## Naming Conventions

**Files:**
- Feature modules use lowercase singular/plural names by domain: `handlers/expenses.py`, `services/budget.py`, `keyboards/shopping.py`.
- Package marker files are `__init__.py` in `handlers/`, `keyboards/`, `services/`, and `state/`.
- Backup/duplicate files use suffixes such as ` (2)` or `.bak_test`; avoid adding new code to these files.

**Directories:**
- Top-level directories are role-based: `handlers/`, `services/`, `keyboards/`, `state/`, `webapp/`.
- Static browser assets live under `webapp/static/`.
- Generated planning docs live under `.planning/codebase/`.

**Functions and Symbols:**
- Public service APIs use snake_case verbs/nouns: `get_budget_limits`, `write_expense`, `get_shopping_items`, `check_access_message`.
- Private helpers use leading underscores: `_load_active_subcategories`, `_safe_delete_prompt`, `_parse_decimal`.
- Keyboard builders use `build_*_keyboard`: `build_main_menu`, `build_confirm_keyboard`, `build_shopping_actions_keyboard`.
- Router modules expose a module-level `router = Router()`.
- Session dataclasses use PascalCase names: `ExpenseSession`, `ShoppingSession`.
- Constants use uppercase: `EXPENSES_SHEET_NAME`, `MENU_EXPENSES_CALLBACK`, `ACCESS_CACHE_TTL_SECONDS`.

## Where to Add New Code

**New Telegram Feature:**
- Primary route code: add a new module under `handlers/` if the feature is large, or extend an existing feature router such as `handlers/menu.py`, `handlers/expenses.py`, or `handlers/shopping.py`.
- Dispatcher registration: include a new router in `app.create_dispatcher` in `app.py`.
- UI controls: add keyboard builders under `keyboards/` and callback constants in `constants.py`.
- Business logic: add service functions under `services/`.
- Session flow: add a dataclass/session store under `state/` only when the feature has multi-step state.

**New Google Sheets Operation:**
- Spreadsheet client access: use `services/google_sheets.py`.
- Sheet names/constants: add names to `constants.py`.
- Domain behavior: add or extend a service module under `services/`, for example `services/budget.py` for budget calculations or `services/shopping.py` for shopping list operations.
- Handler integration: call the service from a router in `handlers/` and catch/log service exceptions in the handler.

**New Expense Capability:**
- Primary code: `handlers/expenses.py` and `services/expenses.py`.
- Category/budget reads: `services/budget.py`.
- Session data: `state/expense_session.py`.
- Keyboards: `keyboards/expenses.py` and possibly `keyboards/limits.py`.

**New Shopping Capability:**
- Primary code: `handlers/shopping.py` and `services/shopping.py`.
- Session data: `state/shopping_session.py`.
- Keyboards: `keyboards/shopping.py`.

**New Menu or Limit View:**
- Primary code: `handlers/menu.py`.
- Keyboards: `keyboards/main.py` or `keyboards/limits.py`.
- Sheet reads: `services/budget.py`, `services/expenses.py`, or a new service under `services/`.

**New Web App Static Asset or Page:**
- HTML/CSS/JS: `webapp/index.html` for the current single page.
- Assets: `webapp/static/`.
- Server routes: `app.create_web_app` in `app.py`.
- Telegram button URL: `WEBAPP_URL` in `config.py` and `keyboards/main.py`.

**Utilities:**
- Spreadsheet/text normalization: `services/google_sheets.py`.
- Shared domain formatting: add a focused helper module under `services/` if formatting is tied to domain data; avoid duplicating helpers in multiple handlers.
- Runtime configuration constants: `constants.py` for non-secret constants and `config.py` for secret-backed names/defaulted runtime settings.

**Tests:**
- No automated test layout is present. New automated tests should use a clearly named test file or test directory instead of extending `test_google.py`, which is a manual integration probe.

## Special Directories

**`handlers/`:**
- Purpose: Telegram routing.
- Generated: No.
- Committed: Yes.

**`keyboards/`:**
- Purpose: Telegram keyboard markup factories.
- Generated: No.
- Committed: Yes.

**`services/`:**
- Purpose: Domain and persistence service functions.
- Generated: No.
- Committed: Yes.

**`state/`:**
- Purpose: In-memory conversation state modules.
- Generated: No.
- Committed: Yes.

**`webapp/`:**
- Purpose: Static Telegram Web App content served from `app.py`.
- Generated: No.
- Committed: Yes.

**`.planning/codebase/`:**
- Purpose: GSD-generated codebase documentation consumed by planning/execution workflows.
- Generated: Yes.
- Committed: Yes when orchestrator chooses to commit planning artifacts.

**`.vscode/`:**
- Purpose: Local editor configuration.
- Generated: No.
- Committed: Ignored by `.gitignore`.

**`__pycache__/`:**
- Purpose: Python bytecode cache.
- Generated: Yes.
- Committed: No.

---

*Structure analysis: 2026-06-29*
