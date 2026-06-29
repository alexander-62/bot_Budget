# Codebase Concerns

**Analysis Date:** 2026-06-29

## Tech Debt

**Synchronous Google Sheets access inside async bot handlers:**
- Issue: All `gspread` calls run synchronously on the aiogram event loop. Handlers call service functions directly, so network latency blocks unrelated updates.
- Files: `handlers/menu.py`, `handlers/expenses.py`, `handlers/shopping.py`, `services/access.py`, `services/budget.py`, `services/expenses.py`, `services/shopping.py`, `services/google_sheets.py`
- Impact: A slow Google Sheets request can delay every Telegram message, callback answer, startup notification, and Web App health route served by the same process.
- Fix approach: Move Sheets operations behind an async boundary using `asyncio.to_thread`, a bounded executor, or an async storage adapter. Keep handler functions responsible for Telegram I/O and make service calls explicitly async.

**Repeated spreadsheet client creation:**
- Issue: `services/google_sheets.py` creates a new `gspread.service_account(...)` client and opens the spreadsheet on every `get_spreadsheet()` call.
- Files: `services/google_sheets.py`, `services/access.py`, `services/budget.py`, `services/expenses.py`, `services/shopping.py`
- Impact: Repeated auth/client setup increases latency, quota pressure, and failure points across high-traffic operations such as limits display and expense creation.
- Fix approach: Cache the authorized client and spreadsheet object with controlled invalidation. Add a thin repository layer so retry/backoff and caching behavior is centralized in `services/google_sheets.py`.

**Duplicate and backup source files in the repo root:**
- Issue: Runtime-like copies and backups coexist with active modules: `handlers/expenses (2).py`, `services/expenses (2).py`, `app.py.bak_test`, `keyboards/main.py.bak_test`, `BOT_TZ (2).md`, and `keyboards/_write_test.tmp`.
- Files: `handlers/expenses (2).py`, `services/expenses (2).py`, `app.py.bak_test`, `keyboards/main.py.bak_test`, `BOT_TZ (2).md`, `keyboards/_write_test.tmp`
- Impact: Future edits can land in the wrong copy, grep/search results are noisy, and duplicate files can accidentally be imported or committed as real implementation.
- Fix approach: Remove obsolete copies from version control and add ignore rules for local scratch files such as `*.bak_test`, `*_write_test.tmp`, and copied `* (2).*` artifacts.

**Repository index contains a deleted duplicate tree:**
- Issue: `git status` reports deleted tracked files under `Новая папка/...`, including duplicate `handlers`, `keyboards`, `services`, and `state` modules.
- Files: `Новая папка/handlers/expenses.py`, `Новая папка/handlers/menu.py`, `Новая папка/handlers/shopping.py`, `Новая папка/services/budget.py`, `Новая папка/state/expense_session.py`
- Impact: The working tree has large unrelated deletion noise, making reviews, merges, and release commits difficult to reason about.
- Fix approach: Decide whether the `Новая папка/` tree is intentionally removed; then either commit the deletion explicitly or restore/move it outside the repository.

**Unpinned dependencies:**
- Issue: `requirements.txt` uses broad requirements only: `aiogram>=3.0.0` and `gspread`.
- Files: `requirements.txt`
- Impact: Installs can resolve to different major/minor behavior over time, especially for aiogram models and Telegram API types used in `keyboards/*.py`.
- Fix approach: Pin known-good versions or generate a lock file. Add a dependency update workflow that runs import/build checks before accepting newer aiogram or gspread releases.

**Manual restart command embedded in chat flow:**
- Issue: Any allowed Telegram user can trigger process restart through the text command handled by `handlers/menu.py`.
- Files: `handlers/menu.py`, `services/access.py`
- Impact: Operational control is mixed with user-facing menu behavior. Accidental or unauthorized use by any allowed sheet user can interrupt active sessions.
- Fix approach: Restrict restart to an admin list separate from general access, move admin commands into a separate router, and log the requester by stable user id as well as username.

## Known Bugs

**Runtime dependencies missing from the local environment:**
- Symptoms: Importing bot UI code fails with `ModuleNotFoundError: No module named 'aiogram'` in the current workspace Python environment.
- Files: `requirements.txt`, `keyboards/expenses.py`, `app.py`
- Trigger: Run `python -c "from keyboards.expenses import build_cancel_keyboard"` without installing requirements.
- Workaround: Install `requirements.txt` into the active environment before running bot checks. Use a `.venv` consistently and document the setup command in `README.md`.

**Potential unsupported inline keyboard button style arguments:**
- Symptoms: Inline keyboard builders pass `style="primary"`, `style="danger"`, `style="success"`, and `style="default"` into `aiogram.types.InlineKeyboardButton`.
- Files: `keyboards/expenses.py`, `keyboards/limits.py`, `keyboards/shopping.py`
- Trigger: Build inline keyboards under aiogram versions that reject or ignore extra model fields.
- Workaround: Remove `style` from Telegram inline button constructors and keep only Bot API-supported fields such as `text`, `callback_data`, `url`, and `web_app`.

**Remote restart does not clean up the aiohttp Web App runner:**
- Symptoms: The restart path calls `os.execv(...)` from a background task without following the normal `app.py` cleanup path.
- Files: `handlers/menu.py`, `app.py`
- Trigger: Allowed user sends the restart text handled by `restart_handler`.
- Workaround: Route restarts through the process manager in `manage_bot.py` or coordinate shutdown through the dispatcher so `web_runner.cleanup()` runs before process replacement.

**Expense row allocation can race under concurrent writes:**
- Symptoms: `services/expenses.py` scans existing rows to compute `next_row`, then writes to that row with `worksheet.update(...)`.
- Files: `services/expenses.py`
- Trigger: Two users finalize expenses at nearly the same time.
- Workaround: Use append semantics with a single API call, a sheet-side append endpoint, or an external lock around row allocation and write.

**Shopping list row allocation can race under concurrent adds:**
- Symptoms: `services/shopping.py` reads column A, computes `next_row`, then writes to that row.
- Files: `services/shopping.py`
- Trigger: Two users add shopping items at nearly the same time.
- Workaround: Use append semantics or serialize shopping mutations through a per-sheet lock.

## Security Considerations

**Local secret files are required for runtime:**
- Risk: The application depends on local `secrets.py` and `credentials.json`; these names are ignored but present in the workspace. Accidental copying, backup, or manual sharing can leak the Telegram token, spreadsheet id, or Google service-account material.
- Files: `secrets.py`, `credentials.json`, `.gitignore`, `config.py`, `services/google_sheets.py`
- Current mitigation: `.gitignore` excludes `secrets.py`, `.env`, `*.env`, `credentials.json`, `.bot.pid`, and `bot.log`.
- Recommendations: Keep secrets outside the repo directory or load them from environment variables/secret manager. Add a startup validation message that lists missing variable names only.

**Access control relies on mutable Telegram usernames:**
- Risk: `services/access.py` authorizes by username from the `Users` worksheet and then syncs chat/user id after a username match.
- Files: `services/access.py`
- Current mitigation: `sync_allowed_user_chat_id(...)` stores a numeric id after a successful username authorization.
- Recommendations: Authorize primarily by immutable Telegram user id. Use usernames only for display and onboarding.

**Spreadsheet URL exposed to all allowed users:**
- Risk: `handlers/menu.py` sends a direct Google Sheets edit URL to any allowed user viewing recent expenses.
- Files: `handlers/menu.py`, `services/google_sheets.py`
- Current mitigation: Telegram access checks run before the recent-expenses handler.
- Recommendations: Confirm that every allowed bot user should also have spreadsheet edit access. Prefer view-only links or bot-mediated actions for non-admin users.

**Logs contain personal and financial context:**
- Risk: Logs include usernames, user ids, categories, subcategories, amounts, shopping items, and restart requester identity.
- Files: `handlers/expenses.py`, `handlers/shopping.py`, `handlers/menu.py`, `manage_bot.py`, `bot.log`
- Current mitigation: `bot.log` is ignored by `.gitignore`.
- Recommendations: Redact or reduce financial details in logs, rotate local logs, and keep logs outside synced/shared folders when possible.

## Performance Bottlenecks

**Budget display performs multiple full-sheet reads:**
- Problem: `get_budget_limits()`, `get_month_totals()`, and `get_category_details()` repeatedly load categories, limits, and expenses with `get_all_values()`.
- Files: `services/budget.py`, `handlers/menu.py`, `handlers/expenses.py`
- Cause: Service functions are composed in handlers without sharing loaded worksheet data.
- Improvement path: Load a monthly snapshot once per request, cache short-lived read results, and pass parsed structures into formatting functions.

**Recent expenses reads the full expense sheet:**
- Problem: `get_recent_expenses(limit=5)` loads all rows and only then returns the last entries.
- Files: `services/expenses.py`, `handlers/menu.py`
- Cause: The implementation has no indexed or range-limited read path.
- Improvement path: Read only the populated tail range, maintain an append-only index, or store recent rows in a small cache after writes.

**Shopping mutations call Google Sheets repeatedly per user message:**
- Problem: Adding comma-separated shopping items calls `add_shopping_item(...)` once per item, and each call reloads existing entries.
- Files: `handlers/shopping.py`, `services/shopping.py`
- Cause: Deduplication and writes are implemented item-by-item.
- Improvement path: Load entries once, deduplicate all requested items in memory, and batch append new rows.

**Startup notification blocks bot readiness on Sheets and Telegram sends:**
- Problem: `notify_startup(...)` loads allowed chat ids and sends startup messages before polling starts.
- Files: `app.py`, `services/access.py`
- Cause: Startup notification is awaited before `dp.start_polling(bot)`.
- Improvement path: Start polling first or run startup notifications in a background task with timeout and backoff.

## Fragile Areas

**In-memory sessions:**
- Files: `state/expense_session.py`, `state/shopping_session.py`, `handlers/expenses.py`, `handlers/shopping.py`
- Why fragile: Sessions live in process-level dictionaries keyed by user id. Restart, crash, deploy, or multi-process execution drops active flows and invalidates callbacks.
- Safe modification: Keep current in-memory behavior for single-process local bot use, but add a session storage abstraction before adding multi-instance deployment or long-running workflows.
- Test coverage: No automated tests cover stale session behavior, concurrent sessions, restart recovery, or callback replay.

**Google Sheets schema is position-based:**
- Files: `services/access.py`, `services/budget.py`, `services/expenses.py`, `services/shopping.py`, `constants.py`
- Why fragile: Code depends on fixed column indexes and exact sheet names. Renaming columns, reordering sheets, or changing a header silently changes behavior.
- Safe modification: Add schema validation at startup that checks required worksheets and headers by name. Keep all column mappings in one module.
- Test coverage: No tests validate worksheet schemas, missing columns, invalid month columns, or malformed numeric values.

**Formatting helpers are duplicated:**
- Files: `handlers/menu.py`, `handlers/expenses.py`
- Why fragile: `_parse_sheet_number`, `_format_eur_rounded`, `_format_money_or_dash`, and `_format_remaining_with_alert` are duplicated with similar behavior.
- Safe modification: Move money parsing/formatting into a shared helper such as `services/formatting.py` and test it with real sheet value formats.
- Test coverage: No tests cover currency formatting, negative remaining alerts, or invalid sheet values.

**Import and route ordering controls broad text capture:**
- Files: `app.py`, `handlers/expenses.py`, `handlers/shopping.py`, `handlers/menu.py`
- Why fragile: `create_dispatcher()` includes shopping, expenses, then menu. Both shopping and expense modules register broad message handlers for any text while a session exists.
- Safe modification: Keep broad handlers near the end of each router and add tests for overlapping active-session scenarios before changing router order.
- Test coverage: No dispatcher-level tests cover route precedence or fallback behavior.

**Encoding/console display is inconsistent:**
- Files: `README.md`, `bot.py`, `keyboards/limits.py`, `keyboards/main.py.bak_test`, `BOT_TZ.md`
- Why fragile: Some files or command outputs display mojibake in the local PowerShell session, while active source files mix Russian text and emoji.
- Safe modification: Enforce UTF-8 via `.editorconfig`, normalize files to UTF-8, and avoid editing localized text in tools configured for legacy encodings.
- Test coverage: No tests assert user-facing Russian strings or generated Telegram message text.

## Scaling Limits

**Single-process in-memory bot state:**
- Current capacity: One process with volatile sessions and module-level access caches.
- Limit: Multiple bot processes, container restarts, or process replacement lose user flow state and produce inconsistent access-cache state.
- Scaling path: Move sessions and authorization cache to Redis, SQLite, or another shared store before scaling beyond one process.

**Google Sheets as primary database:**
- Current capacity: Suitable for small household/team usage with low concurrent writes.
- Limit: Row scans, column scans, and per-item updates become slow and quota-prone as expenses and shopping rows grow.
- Scaling path: Introduce a database-backed repository for expenses/shopping, then sync summary views to Google Sheets if spreadsheet visibility remains required.

**Web App is static and served from the bot process:**
- Current capacity: Serves `webapp/index.html` and `webapp/static/logo.png` from the same aiohttp process as the Telegram bot.
- Limit: Static hosting, bot polling, Sheets calls, and health checks share the same event loop and process lifetime.
- Scaling path: Move Web App assets to a static host or separate aiohttp service if the Web App becomes interactive or high traffic.

## Dependencies at Risk

**aiogram:**
- Risk: Version floor only (`aiogram>=3.0.0`) allows changes in Pydantic model strictness, Telegram API model fields, and dispatcher behavior.
- Impact: Keyboard construction, handler registration, and bot startup can fail after a fresh install.
- Migration plan: Pin an aiogram minor version and add a smoke test that imports `app.py`, builds all keyboards, and creates a dispatcher.

**gspread:**
- Risk: Unpinned `gspread` can change auth, worksheet update signatures, or default value rendering.
- Impact: Reads/writes in `services/google_sheets.py`, `services/expenses.py`, and `services/shopping.py` can fail or produce unexpected sheet values.
- Migration plan: Pin a known-good version and wrap all Sheets API calls in a small adapter with focused tests/mocks.

**Google Sheets worksheet contract:**
- Risk: Sheet names and columns are external runtime dependencies rather than code-owned schema.
- Impact: Bot features fail when a worksheet is renamed, column order changes, or month headers are missing.
- Migration plan: Add a schema verification command that checks `Users`, categories, limits, expenses, and shopping worksheets before bot startup.

## Missing Critical Features

**Automated test suite:**
- Problem: The repository has `test_google.py`, but it is a manual live script that reads credentials and appends to the real spreadsheet.
- Blocks: Safe refactoring of handlers, parsers, access checks, and Google Sheets adapters.

**Configuration validation:**
- Problem: `config.py` imports required settings from `secrets.py` directly and does not validate missing or malformed configuration with actionable errors.
- Blocks: Reliable first-run setup, deployment diagnostics, and CI smoke checks.

**Admin role separation:**
- Problem: Allowed users and operators are the same access group for restart behavior and spreadsheet link exposure.
- Blocks: Least-privilege operation for household/team users who should submit expenses without controlling process lifecycle.

**Schema migration/initialization tooling:**
- Problem: No command creates or validates the required Google Sheets worksheets and headers.
- Blocks: Reproducible setup and safe changes to expense or budget sheet layout.

## Test Coverage Gaps

**Parsing and formatting:**
- What's not tested: Amount parsing, optional comments, decimal rounding, money display, negative remaining indicators, invalid sheet numbers.
- Files: `services/expenses.py`, `handlers/menu.py`, `handlers/expenses.py`
- Risk: User-facing financial values can be parsed, rounded, or displayed incorrectly.
- Priority: High

**Authorization:**
- What's not tested: Username normalization, empty username rejection, user id sync, cache TTL behavior, malformed `Users` rows.
- Files: `services/access.py`
- Risk: Access can fail closed for valid users, stay stale after sheet edits, or rely on mutable usernames longer than intended.
- Priority: High

**Sheets adapters and schema handling:**
- What's not tested: Missing worksheets, missing month column, duplicate categories, invalid sort order, malformed numeric values, Google API failures.
- Files: `services/google_sheets.py`, `services/budget.py`, `services/expenses.py`, `services/shopping.py`
- Risk: Spreadsheet layout changes break the bot at runtime without clear diagnostics.
- Priority: High

**Conversation flows:**
- What's not tested: Expense category/subcategory selection, stale callbacks, cancel behavior, comment editing, shopping add/remove/clear flows.
- Files: `handlers/expenses.py`, `handlers/shopping.py`, `state/expense_session.py`, `state/shopping_session.py`
- Risk: Handler changes can break multi-step interactions silently.
- Priority: Medium

**Process management and startup:**
- What's not tested: Background start/stop, stale PID cleanup, remote restart, Web App server cleanup, startup notifications.
- Files: `manage_bot.py`, `app.py`, `handlers/menu.py`
- Risk: Operational commands can leave stale PID files, orphan processes, or unavailable Web App routes.
- Priority: Medium

---

*Concerns audit: 2026-06-29*
