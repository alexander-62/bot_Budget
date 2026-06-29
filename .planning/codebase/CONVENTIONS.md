# Coding Conventions

**Analysis Date:** 2026-06-29

## Naming Patterns

**Files:**
- Use lowercase snake_case Python module names for active code: `services/google_sheets.py`, `state/expense_session.py`, `keyboards/shopping.py`.
- Keep feature files grouped by role, not by vertical package: handlers in `handlers/`, keyboard builders in `keyboards/`, data/service logic in `services/`, session state in `state/`.
- Avoid duplicate backup-style active modules. Files such as `handlers/expenses (2).py`, `services/expenses (2).py`, `app.py.bak_test`, and `keyboards/main.py.bak_test` exist beside active modules but are not imported by `app.py`.
- Root scripts use short operational names: `app.py` owns runtime setup, `bot.py` delegates to `app.main`, `manage_bot.py` owns process management, and `test_google.py` is a manual Google Sheets smoke script.

**Functions:**
- Use snake_case for public functions: `create_dispatcher()` in `app.py`, `get_budget_limits()` in `services/budget.py`, `build_main_menu()` in `keyboards/main.py`.
- Prefix module-private helpers with `_`: `_parse_sheet_number()` in `handlers/menu.py`, `_load_active_subcategories()` in `services/budget.py`, `_safe_delete_prompt()` in `handlers/shopping.py`.
- Handler functions are async and named after user flow/action: `start_expense_flow()` in `handlers/expenses.py`, `shopping_action_handler()` in `handlers/shopping.py`, `fallback_handler()` in `handlers/menu.py`.
- Service functions are synchronous and verb-oriented: `write_expense()` in `services/expenses.py`, `clear_shopping_list()` in `services/shopping.py`, `sync_allowed_user_chat_id()` in `services/access.py`.

**Variables:**
- Module-level constants use UPPER_SNAKE_CASE: `USERS_SHEET_NAME` and `ACCESS_CACHE_TTL_SECONDS` in `constants.py`, `BOT_TOKEN` and `SPREADSHEET_ID` in `config.py`.
- Module-level mutable state uses leading underscore: `_expense_sessions` in `state/expense_session.py`, `_shopping_sessions` in `state/shopping_session.py`, `_allowed_usernames_cache` in `services/access.py`.
- Callback/session identifiers use explicit names: `session_id`, `idx_raw`, `category_idx_raw`, `user_id` in `handlers/expenses.py` and `handlers/menu.py`.
- Google Sheets row values use descriptive suffixes like `_raw`, `_value`, and `_idx`: `sort_order_raw` in `services/budget.py`, `username_value` in `services/expenses.py`, `row_idx` in `services/shopping.py`.

**Types:**
- Use dataclasses for state records and simple domain records: `ExpenseSession` in `state/expense_session.py`, `ShoppingSession` in `state/shopping_session.py`, `ActiveSubcategory` in `services/budget.py`.
- Use modern Python type syntax: `str | None`, `list[str]`, `dict[tuple[str, str], Decimal]`, and tuple return annotations appear across `services/budget.py`, `services/expenses.py`, and `state/*.py`.
- Annotate public service and helper returns. Most active modules include return types, e.g. `get_recent_expenses()` in `services/expenses.py` and `create_web_app()` in `app.py`.
- Use `Decimal` for money parsing/formatting logic in `services/expenses.py`, `services/budget.py`, `handlers/menu.py`, and `handlers/expenses.py`.

## Code Style

**Formatting:**
- Configured editor style is minimal: `.editorconfig` sets UTF-8, LF line endings, and final newline.
- No formatter config is present: `pyproject.toml`, Black, Ruff, Flake8, or isort configuration is not detected.
- Use 4-space indentation and standard Python layout.
- Keep imports separated into standard library, third-party, and local groups as seen in `app.py`, `handlers/menu.py`, and `services/budget.py`.
- Wrap long function calls and keyboard definitions over multiple lines as in `keyboards/main.py` and `handlers/shopping.py`.
- Preserve UTF-8 text. Several files contain readable UTF-8 Russian text (`services/access.py`, `constants.py`, `keyboards/main.py`), while several files render mojibake in source (`handlers/expenses.py`, `handlers/menu.py`, `keyboards/expenses.py`); new changes should use valid UTF-8 consistently.

**Linting:**
- Not detected. No lint command or config file is present.
- Follow the local typed, explicit style instead of introducing untyped helpers.
- Keep root runtime files small where possible. Existing large handlers include `handlers/expenses.py` and `handlers/shopping.py`; new flow-specific complexity should usually go into services or state helpers.

## Import Organization

**Order:**
1. Standard library imports: `asyncio`, `logging`, `pathlib.Path` in `app.py`; `datetime`, `decimal`, `collections` in `services/budget.py`.
2. Third-party imports: `aiohttp.web`, `aiogram`, and `gspread` in `app.py`, `handlers/*.py`, and `services/*.py`.
3. Local absolute imports from top-level packages: `constants`, `config`, `handlers`, `keyboards`, `services`, and `state`.

**Path Aliases:**
- Not detected. Imports are plain absolute imports rooted at the repository root, e.g. `from services.google_sheets import get_spreadsheet` in `services/budget.py`.
- Do not add relative imports inside packages unless the repo packaging model changes. Existing modules consistently use imports such as `from keyboards.main import build_main_menu`.

## Error Handling

**Patterns:**
- Handler modules catch broad external failures at the user-interaction boundary, log stack traces with `logging.exception(...)`, and send a friendly Telegram response. Examples: `_send_limits()` in `handlers/menu.py`, `_show_shopping_list()` in `handlers/shopping.py`, `_finalize_expense()` in `handlers/expenses.py`.
- Validation helpers raise `ValueError` with user-facing messages. Examples: `parse_amount()` in `services/expenses.py`, `remove_shopping_item_by_number()` in `services/shopping.py`, `find_worksheet_case_insensitive()` in `services/google_sheets.py`.
- Service parsing helpers convert malformed spreadsheet values into defaults when appropriate: `_parse_decimal()` in `services/budget.py` returns `Decimal("0")` for invalid values.
- Access checks return explicit status tuples: `is_allowed_username()` in `services/access.py` returns `(bool, reason)` where reason is `"empty_username"` or `"username_not_found"`.
- Cleanup helpers intentionally swallow message-deletion failures after logging: `_safe_delete_prompt()` exists in both `handlers/expenses.py` and `handlers/shopping.py`.
- Process management handles missing or stale PID files by returning early and printing status in `manage_bot.py`.

## Logging

**Framework:** Python standard `logging`.

**Patterns:**
- Configure logging once in `setup_logging()` in `app.py` with an INFO root level and reduced aiogram noise.
- Use `logging.exception(...)` inside `except` blocks where stack traces are useful for Google Sheets, Telegram, or filesystem failures.
- Use structured message templates with `%s` placeholders for event logs: `expense_added` in `handlers/expenses.py`, `shopping_add` and `shopping_remove` in `handlers/shopping.py`.
- Use `logging.warning(...)` for recoverable bad data or sensitive operational events: invalid chat IDs in `services/access.py`, remote restart requests in `handlers/menu.py`.
- CLI-only tooling uses `print(...)` for operator feedback in `manage_bot.py`; bot/runtime modules should use `logging`.

## Comments

**When to Comment:**
- Comments are sparse in active modules. Prefer clear function names and small helpers.
- Add comments only for operational context or non-obvious external behavior, such as Google Sheets column assumptions or Telegram callback payload formats.
- Avoid comments that repeat code mechanics. Existing code generally omits such comments in `services/budget.py`, `services/shopping.py`, and `state/*.py`.
- `test_google.py` includes manual-step comments; keep this style limited to scripts intended for human execution.

**JSDoc/TSDoc:**
- Not applicable. This is a Python codebase.
- Python docstrings are not used consistently. Prefer type hints plus self-descriptive function names unless adding a complex public service contract.

## Function Design

**Size:** 
- Keep pure service helpers compact and single-purpose, following `normalize_text()` in `services/google_sheets.py`, `_format_decimal()` in `services/budget.py`, and `parse_amount()` in `services/expenses.py`.
- Handler functions may orchestrate async user flows, but should delegate parsing, persistence, keyboard construction, and state storage to `services/`, `keyboards/`, and `state/`.
- For new complex flows, follow the split used by `handlers/expenses.py`: small private helpers for formatting, loading, cancellation, and finalization plus registered router handlers for entry points.

**Parameters:** 
- Pass explicit primitives and data objects. Examples: `write_expense(username, category, subcategory, amount, comment)` in `services/expenses.py`, `create_session(user_id, state)` in `state/expense_session.py`.
- Prefer `types.Message` and `types.CallbackQuery` parameters at handler boundaries, not inside service modules.
- Keep optional Telegram fields typed as nullable: `chat_id: int | None`, `message_id: int | None`, `username: str | None`.

**Return Values:** 
- Return typed domain values from service functions: tuples/lists from `get_budget_limits()`, `get_category_details()`, `get_shopping_entries()`, and `get_recent_expenses()`.
- Return `None` for side-effecting write operations: `write_expense()`, `clear_shopping_list()`, and `sync_allowed_user_chat_id()`.
- Return booleans from access guard functions: `check_access_message()` and `check_access_callback()` in `services/access.py`.
- Raise `ValueError` for expected validation failures and let handlers map them to user messages.

## Module Design

**Exports:** 
- Modules export functions directly; no `__all__` declarations are used.
- `handlers/*.py` modules expose a module-level `router = Router()` that `app.create_dispatcher()` imports and includes.
- `keyboards/*.py` modules expose `build_*_keyboard()` functions returning aiogram markup objects.
- `services/*.py` modules expose synchronous data and validation helpers. External API details are centralized mostly in `services/google_sheets.py`.
- `state/*.py` modules expose dataclasses and functions around module-level in-memory dictionaries.

**Barrel Files:** 
- `handlers/__init__.py`, `keyboards/__init__.py`, `services/__init__.py`, and `state/__init__.py` exist but are empty. Do not add barrel imports unless the repo adopts that pattern consistently.

---

*Convention analysis: 2026-06-29*
