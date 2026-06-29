<!-- refreshed: 2026-06-29 -->
# Architecture

**Analysis Date:** 2026-06-29

## System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│                    Runtime Entrypoints                      │
├──────────────────┬──────────────────┬───────────────────────┤
│ Telegram polling │ Web App server   │ Process manager       │
│ `app.py`         │ `app.py`         │ `manage_bot.py`       │
│ `bot.py`         │ `webapp/`        │ `start_bot.bat`       │
└────────┬─────────┴────────┬─────────┴──────────┬────────────┘
         │                  │                     │
         ▼                  ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│                  aiogram Router Layer                       │
│ `handlers/menu.py`, `handlers/expenses.py`,                 │
│ `handlers/shopping.py`                                      │
└────────┬──────────────────┬─────────────────────┬───────────┘
         │                  │                     │
         ▼                  ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Presentation and Session Helpers                │
│ `keyboards/`, `state/expense_session.py`,                    │
│ `state/shopping_session.py`                                  │
└────────┬────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Domain Service Layer                      │
│ `services/access.py`, `services/budget.py`,                  │
│ `services/expenses.py`, `services/shopping.py`               │
└────────┬────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                Google Sheets Persistence                     │
│ `services/google_sheets.py`, `config.py`, `constants.py`     │
│ secret-bearing files: `secrets.py`, `credentials.json`       │
└─────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Application bootstrap | Configure logging, create aiogram dispatcher, register routers, start aiohttp Web App server, run Telegram polling, send startup notifications. | `app.py` |
| Bot wrapper | Minimal console entry point that imports and runs `app.main`. | `bot.py` |
| Process manager | Start, stop, restart, and inspect a background bot process using `.bot.pid` and `bot.log`. | `manage_bot.py` |
| Menu router | `/start`, main menu actions, limit view, recent expense view, category details, restart command, and fallback routing. | `handlers/menu.py` |
| Expense router | Multi-step expense add flow: choose category, choose subcategory, enter amount/comment, confirm, write expense. | `handlers/expenses.py` |
| Shopping router | Shopping list menu, add/remove/clear flows, session prompt cleanup, Google Sheets list mutations. | `handlers/shopping.py` |
| Keyboard builders | aiogram reply and inline keyboard construction for menus, limits, expenses, and shopping. | `keyboards/main.py`, `keyboards/limits.py`, `keyboards/expenses.py`, `keyboards/shopping.py` |
| Access service | Username authorization, chat id synchronization, startup broadcast recipients, and in-memory access caches. | `services/access.py` |
| Budget service | Budget/category/month calculations over Google Sheets rows. | `services/budget.py` |
| Expense service | Amount parsing, expense row selection, expense writes, recent expense reads. | `services/expenses.py` |
| Shopping service | Shopping list reads, deduped item insertions, indexed deletes, list clear. | `services/shopping.py` |
| Google Sheets adapter | gspread service-account client creation, spreadsheet open, worksheet lookup, common text normalization. | `services/google_sheets.py` |
| Session state | In-memory per-user finite-state session records with TTL checks. | `state/expense_session.py`, `state/shopping_session.py` |
| Static Web App | Telegram Web App page and static logo served by aiohttp. | `webapp/index.html`, `webapp/static/logo.png` |
| Shared constants/config | Sheet names, callback ids, TTLs, UI labels, item length, secret-backed runtime settings. | `constants.py`, `config.py` |

## Pattern Overview

**Overall:** Layered aiogram bot with router modules, procedural service modules, in-memory conversation sessions, and Google Sheets as the persistence boundary.

**Key Characteristics:**
- Keep Telegram update handling in router modules under `handlers/`; routers are included centrally in `app.create_dispatcher` at `app.py:29`.
- Keep durable data access behind service functions in `services/`; all spreadsheet clients flow through `services/google_sheets.py`.
- Keep UI markup construction in `keyboards/`; handlers should call builders instead of assembling keyboard structures inline.
- Keep multi-step conversational state in `state/` dataclasses keyed by Telegram user id; session ids are embedded in callback data.
- Keep runtime settings in `config.py` as names imported from `secrets.py`; never read or commit secret values from `secrets.py` or `credentials.json`.

## Layers

**Entrypoint Layer:**
- Purpose: Start the bot runtime and optional process management.
- Location: `app.py`, `bot.py`, `manage_bot.py`, `start_bot.bat`, `restart_bot.bat`
- Contains: `asyncio.run`, logging setup, aiohttp setup, aiogram dispatcher setup, subprocess/PID management.
- Depends on: `config.py`, `handlers/`, `services/access.py`, Python stdlib process APIs.
- Used by: Console commands from `README.md` and batch files `start_bot.bat`, `restart_bot.bat`.

**Router Layer:**
- Purpose: Translate Telegram messages and callbacks into domain operations and responses.
- Location: `handlers/menu.py`, `handlers/expenses.py`, `handlers/shopping.py`
- Contains: `Router()` instances, `@router.message` handlers, `@router.callback_query` handlers, presentation formatting helpers.
- Depends on: `services/`, `keyboards/`, `state/`, `constants.py`, aiogram types.
- Used by: `app.create_dispatcher` in `app.py`.

**Keyboard Layer:**
- Purpose: Build reply and inline keyboard markup with stable callback data prefixes.
- Location: `keyboards/main.py`, `keyboards/limits.py`, `keyboards/expenses.py`, `keyboards/shopping.py`
- Contains: `build_*_keyboard` functions returning aiogram markup objects.
- Depends on: `constants.py`, `config.py`, aiogram types.
- Used by: `handlers/menu.py`, `handlers/expenses.py`, `handlers/shopping.py`.

**Session Layer:**
- Purpose: Track multi-step Telegram flows between messages/callbacks.
- Location: `state/expense_session.py`, `state/shopping_session.py`
- Contains: dataclasses `ExpenseSession` and `ShoppingSession`, module-level session dictionaries, TTL validation, stale callback detection.
- Depends on: TTL constants in `constants.py`.
- Used by: `handlers/expenses.py`, `handlers/shopping.py`.

**Service Layer:**
- Purpose: Encapsulate domain operations and Google Sheets row/worksheet details.
- Location: `services/access.py`, `services/budget.py`, `services/expenses.py`, `services/shopping.py`
- Contains: authorization checks, budget aggregation, amount parsing, expense writes, shopping list mutations.
- Depends on: `services/google_sheets.py`, `constants.py`, `gspread`, Python stdlib data types.
- Used by: Router modules under `handlers/`.

**Google Sheets Adapter Layer:**
- Purpose: Centralize spreadsheet client creation and worksheet lookup.
- Location: `services/google_sheets.py`
- Contains: `get_spreadsheet`, `get_spreadsheet_url`, `find_worksheet_case_insensitive`, `normalize_text`, `normalize_username`.
- Depends on: `config.py` and `gspread`.
- Used by: `services/access.py`, `services/budget.py`, `services/expenses.py`, `services/shopping.py`.

**Static Web Layer:**
- Purpose: Serve a Telegram Web App test page and static logo from the same Python process.
- Location: `app.py`, `webapp/index.html`, `webapp/static/logo.png`
- Contains: aiohttp routes for `/webapp`, `/webapp/health`, and `/webapp/static/`.
- Depends on: `config.py` for bind host/port and `keyboards/main.py` for the Web App URL used by Telegram.
- Used by: Telegram Web App button in `keyboards/main.py`.

## Data Flow

### Primary Bot Startup Path

1. Console starts `bot.py`, which imports `main` from `app.py` (`bot.py:1`).
2. `app.main` sets logging, starts the Web App server, creates `Bot`, builds the dispatcher, notifies allowed chats, and starts polling (`app.py:88`).
3. `app.create_dispatcher` registers shopping, expense, and menu routers in that order (`app.py:29`).
4. aiogram dispatches updates to router handlers in `handlers/shopping.py`, `handlers/expenses.py`, and `handlers/menu.py`.

### Web App Static Flow

1. `app.create_web_app` resolves `webapp/` and `webapp/static/` from the repository root (`app.py:37`).
2. aiohttp serves `/webapp`, `/webapp/health`, and `/webapp/static/` (`app.py:50`).
3. `keyboards/main.py` exposes a Telegram `KeyboardButton` with `WebAppInfo(url=WEBAPP_URL)` (`keyboards/main.py`).
4. `webapp/index.html` loads Telegram Web App JS and displays `/webapp/static/logo.png` (`webapp/index.html:7`, `webapp/index.html:89`).

### Access Check Flow

1. Every user-facing handler calls `check_access_message` or `check_access_callback` before doing work (`handlers/menu.py`, `handlers/expenses.py`, `handlers/shopping.py`).
2. `services/access.py` loads allowed usernames from the `Users` worksheet through `get_spreadsheet` and `find_worksheet_case_insensitive` (`services/access.py:23`).
3. Successful access syncs Telegram user id/chat id back to the `Users` worksheet (`services/access.py:128`).
4. Access data is cached in module-level dictionaries/sets with `ACCESS_CACHE_TTL_SECONDS` (`services/access.py:39`, `services/access.py:73`, `services/access.py:116`).

### Expense Creation Flow

1. User starts the flow from a reply-keyboard text or `MENU_EXPENSES_CALLBACK` (`handlers/expenses.py:227`, `handlers/expenses.py:235`).
2. Handler loads categories from `services.budget.get_budget_limits` and creates an `ExpenseSession` (`handlers/expenses.py:116`, `state/expense_session.py:28`).
3. Category and subcategory callbacks use `exp:cat:{session_id}:{idx}` and `exp:sub:{session_id}:{idx}` callback data (`handlers/expenses.py:326`, `handlers/expenses.py:386`).
4. Amount text is parsed by `services.expenses.parse_amount_with_optional_comment` (`handlers/expenses.py:246`, `services/expenses.py:28`).
5. Confirmation calls `services.expenses.write_expense`, which writes a row to the expenses worksheet (`handlers/expenses.py:154`, `services/expenses.py:62`).
6. Handler pops the in-memory session and sends an updated category card (`handlers/expenses.py:154`, `state/expense_session.py:48`).

### Shopping List Flow

1. User starts the flow from a reply-keyboard text or `MENU_SHOPPING_CALLBACK` (`handlers/shopping.py:113`, `handlers/shopping.py:121`).
2. Handler loads current items from `services.shopping.get_shopping_items` and creates a `ShoppingSession` (`handlers/shopping.py:53`, `state/shopping_session.py:26`).
3. Shopping action callbacks use `sh:act:{session_id}:add|remove|clear` callback data (`handlers/shopping.py:257`).
4. Text input adds deduplicated items through `services.shopping.add_shopping_item` or removes items by number through `services.shopping.remove_shopping_item_by_number` and `services.shopping.remove_shopping_items_by_numbers` (`handlers/shopping.py:133`, `services/shopping.py:49`, `services/shopping.py:69`, `services/shopping.py:80`).
5. Clear confirmation calls `services.shopping.clear_shopping_list` (`handlers/shopping.py:343`, `services/shopping.py:108`).

**State Management:**
- Telegram conversation state is process-local memory only: `_expense_sessions` in `state/expense_session.py:21` and `_shopping_sessions` in `state/shopping_session.py:19`.
- Access authorization caches are process-local memory only: `_allowed_usernames_cache`, `_allowed_chat_ids_cache`, and `_allowed_user_chat_ids_cache` in `services/access.py`.
- Durable application data lives in Google Sheets worksheets named by constants in `constants.py`.

## Key Abstractions

**aiogram Router Modules:**
- Purpose: Own Telegram routing for a feature area.
- Examples: `handlers/menu.py`, `handlers/expenses.py`, `handlers/shopping.py`
- Pattern: One `router = Router()` per module, included by `app.create_dispatcher`.

**Service Functions:**
- Purpose: Own domain logic and spreadsheet interaction behind procedural APIs.
- Examples: `services/budget.py`, `services/expenses.py`, `services/shopping.py`, `services/access.py`
- Pattern: Handlers call named functions; services raise exceptions for handlers to log and translate into user-facing messages.

**Google Sheets Worksheet Adapter:**
- Purpose: Hide gspread authorization and case-insensitive worksheet lookup.
- Examples: `services/google_sheets.py`
- Pattern: All spreadsheet access should call `get_spreadsheet()` and `find_worksheet_case_insensitive()` rather than constructing gspread clients directly.

**Session Dataclasses:**
- Purpose: Store user-specific flow state and prompt message ids.
- Examples: `state/expense_session.py`, `state/shopping_session.py`
- Pattern: Create session at flow start, mutate `state` field as callbacks/text arrive, call `touch_session`, reject stale session ids.

**Keyboard Builders:**
- Purpose: Keep aiogram markup creation out of service code and make callback data prefixes explicit.
- Examples: `keyboards/expenses.py`, `keyboards/shopping.py`, `keyboards/limits.py`, `keyboards/main.py`
- Pattern: Builder functions accept domain labels/session ids and return markup objects.

## Entry Points

**Bot runtime:**
- Location: `bot.py`
- Triggers: `python bot.py`, `manage_bot.py` subprocess, batch files.
- Responsibilities: Import and run `app.main` with `asyncio.run`.

**Application runtime:**
- Location: `app.py`
- Triggers: direct `python app.py` or indirect `bot.py`.
- Responsibilities: Logging, dispatcher, aiohttp Web App server, bot polling, startup notification.

**Process manager CLI:**
- Location: `manage_bot.py`
- Triggers: `python manage_bot.py start|stop|restart|status`, `start_bot.bat`, `restart_bot.bat`.
- Responsibilities: Background process lifecycle, `.bot.pid`, `bot.log`.

**Telegram handlers:**
- Location: `handlers/menu.py`, `handlers/expenses.py`, `handlers/shopping.py`
- Triggers: aiogram messages and callback queries.
- Responsibilities: Access checks, session transitions, service calls, response messages and keyboards.

**Web App endpoint:**
- Location: `app.py`, `webapp/index.html`
- Triggers: HTTP GET `/webapp`, Telegram Web App button.
- Responsibilities: Static page delivery and Telegram Web App client initialization.

**Google connectivity probe:**
- Location: `test_google.py`
- Triggers: direct `python test_google.py`.
- Responsibilities: Manual gspread connection and sample append using secret-backed config names.

## Architectural Constraints

- **Threading:** Runtime is an asyncio event loop driven by aiogram and aiohttp in one process; service calls to gspread are synchronous and run inside async handlers.
- **Global state:** `state/expense_session.py`, `state/shopping_session.py`, and `services/access.py` keep process-local mutable dictionaries/sets that reset on process restart.
- **Router order:** `app.create_dispatcher` includes `shopping_router`, then `expenses_router`, then `menu_router`; broad text handlers in shopping/expenses rely on active session predicates before `handlers/menu.py` fallback catches unmatched messages.
- **Persistence:** Google Sheets is the durable store; no local database, migration layer, repository abstraction, or transaction boundary is present.
- **Configuration:** `config.py` imports names from `secrets.py`; `secrets.py` and `credentials.json` are secret-bearing files and are excluded from content documentation.
- **Circular imports:** No circular import chain is apparent in the active module path; services depend downward on `services/google_sheets.py` and constants, while handlers depend on services/keyboards/state.
- **Encoding:** Several source files contain mojibake-looking Russian strings while `.editorconfig` declares UTF-8; preserve current file encoding behavior when editing user-facing text.

## Anti-Patterns

### Direct Spreadsheet Access Outside the Adapter

**What happens:** `test_google.py` imports `gspread` and secret config names directly for a manual probe.
**Why it's wrong:** Runtime code should not duplicate spreadsheet authorization and sheet opening logic because `services/google_sheets.py` is the central adapter.
**Do this instead:** Add production spreadsheet operations to service modules that call `services/google_sheets.py`; keep one-off probes isolated in `test_google.py`.

### Feature Handler Modules Owning Presentation Formatting

**What happens:** `handlers/menu.py` and `handlers/expenses.py` both define money parsing/formatting helpers with overlapping behavior.
**Why it's wrong:** Repeated formatting logic can drift across limit cards and expense cards.
**Do this instead:** For new shared formatting, add a small helper module under `services/` or a dedicated utility module and call it from `handlers/menu.py` and `handlers/expenses.py`.

### Backup/Duplicate Files in Runtime Folders

**What happens:** Files such as `handlers/expenses (2).py`, `services/expenses (2).py`, `app.py.bak_test`, and `keyboards/main.py.bak_test` sit beside active runtime files.
**Why it's wrong:** They are not imported by the active runtime path but can confuse future edits and mapper searches.
**Do this instead:** Treat active files without ` (2)` or `.bak_test` suffixes as authoritative: `handlers/expenses.py`, `services/expenses.py`, `app.py`, `keyboards/main.py`.

### Synchronous I/O Inside Async Handlers

**What happens:** Async handlers call gspread-backed service functions directly, for example `handlers/expenses.py` calls `write_expense` and `handlers/shopping.py` calls shopping service mutations.
**Why it's wrong:** Slow Google Sheets requests block the event loop and delay other updates.
**Do this instead:** Keep the same service boundary for new code, and consider wrapping blocking service calls in an executor if responsiveness becomes a requirement.

## Error Handling

**Strategy:** Handlers catch broad exceptions around service calls, log stack traces with `logging.exception`, and send short user-facing retry/error messages. Services generally raise `ValueError` for validation/domain failures and let Google/gspread failures propagate.

**Patterns:**
- Access failures are translated inside `services/access.py` async helpers (`check_access_message`, `check_access_callback`).
- Handler-level service failures are logged in `handlers/menu.py`, `handlers/expenses.py`, and `handlers/shopping.py`.
- Validation failures from amount and shopping parsing are caught and shown to the user without stack traces.
- Startup notification failures are logged per chat id and do not stop bot startup in `app.notify_startup`.

## Cross-Cutting Concerns

**Logging:** `app.setup_logging` configures root logging and reduces aiogram noise; feature handlers log meaningful operation failures and some successful mutations in `handlers/expenses.py` and `handlers/shopping.py`.
**Validation:** Access validation is centralized in `services/access.py`; amount validation is in `services/expenses.py`; callback/session validation is in handler predicates and `state/*_session.py`.
**Authentication:** Telegram users are authorized by username from the `Users` worksheet, with chat id synchronization in `services/access.py`.
**Configuration:** Secret-backed settings are exposed through `config.py` as `BOT_TOKEN`, `GOOGLE_CREDENTIALS_FILE`, `SPREADSHEET_ID`, `WEBAPP_URL`, `WEBAPP_HOST`, and `WEBAPP_PORT`.
**Data ownership:** Sheet names and callback constants live in `constants.py`; row layouts are embedded in service modules that read/write each worksheet.

---

*Architecture analysis: 2026-06-29*
