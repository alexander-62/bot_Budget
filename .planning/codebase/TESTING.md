# Testing Patterns

**Analysis Date:** 2026-06-29

## Test Framework

**Runner:**
- Not detected. No `pytest`, `unittest`, `tox`, `nox`, or test runner configuration is present.
- Config: Not detected. No `pyproject.toml`, `pytest.ini`, `setup.cfg`, `tox.ini`, or coverage config is present.
- Existing test-like file: `test_google.py` is an executable integration smoke script, not an automated assertion-based test suite.

**Assertion Library:**
- Not detected. No `assert`, `unittest.TestCase`, or matcher/assertion framework usage is present in active test files.

**Run Commands:**
```bash
python test_google.py         # Manual live Google Sheets smoke script; reads and appends data
python -m py_compile app.py bot.py manage_bot.py services/*.py handlers/*.py keyboards/*.py state/*.py  # Syntax smoke check
# Watch mode: Not detected
# Coverage: Not detected
```

## Test File Organization

**Location:**
- Only one test-named file is present at the repository root: `test_google.py`.
- No `tests/` directory exists.
- No co-located unit test files exist under `handlers/`, `services/`, `keyboards/`, or `state/`.

**Naming:**
- Existing pattern: root-level `test_*.py`, currently only `test_google.py`.
- Future automated tests should use `test_*.py` under a `tests/` directory or co-located beside the module only if the repo adopts pytest.
- Avoid backup-style pseudo-test filenames such as `app.py.bak_test` and `keyboards/main.py.bak_test`; these are not runner-discoverable tests.

**Structure:**
```text
bot_Budget/
├── test_google.py        # Manual Google Sheets smoke script
├── services/             # No automated service tests detected
├── handlers/             # No automated handler tests detected
├── keyboards/            # No automated keyboard tests detected
└── state/                # No automated state tests detected
```

## Test Structure

**Suite Organization:**
```python
# Current pattern in test_google.py
def main() -> None:
    gc = gspread.service_account(filename=GOOGLE_CREDENTIALS_FILE)
    sh = gc.open_by_key(SPREADSHEET_ID)
    worksheet = sh.sheet1
    all_records = worksheet.get_all_records()
    print("...")
    worksheet.append_row([...])

if __name__ == "__main__":
    main()
```

**Patterns:**
- Manual script setup imports real credentials names from `secrets.py` in `test_google.py`.
- The script uses the real `gspread.service_account(...)` client and real spreadsheet ID.
- The script verifies behavior by printing records and appending a sample row, not by assertions.
- No automated setup/teardown pattern is present.
- No isolated test data cleanup pattern is present.

## Mocking

**Framework:** Not detected.

**Patterns:**
```python
# No mocking pattern exists in the repo.
# Service code currently calls Google Sheets directly:
spreadsheet = get_spreadsheet()
worksheet = find_worksheet_case_insensitive(spreadsheet, EXPENSES_SHEET_NAME)
```

**What to Mock:**
- Mock `services.google_sheets.get_spreadsheet()` for service tests around `services/budget.py`, `services/expenses.py`, `services/shopping.py`, and `services/access.py`.
- Mock worksheet methods such as `get_all_values()`, `col_values()`, `update()`, `update_cell()`, `delete_rows()`, and `batch_clear()` when testing Google Sheets behavior.
- Mock aiogram `types.Message`, `types.CallbackQuery`, and `bot.delete_message()` when testing `handlers/expenses.py`, `handlers/shopping.py`, and `handlers/menu.py`.
- Mock monotonic/time behavior when testing session expiration in `state/expense_session.py` and `state/shopping_session.py`.

**What NOT to Mock:**
- Do not mock pure parsing and formatting helpers such as `parse_amount()` in `services/expenses.py`, `normalize_text()` in `services/google_sheets.py`, `_parse_decimal()` in `services/budget.py`, or `_format_shopping_list()` in `handlers/shopping.py`.
- Do not use live `credentials.json`, `secrets.py`, or a real Google Sheet for normal automated unit tests.
- Do not mock `Decimal` behavior; test money parsing/rounding with concrete input/output values.

## Fixtures and Factories

**Test Data:**
```python
# Suggested shape based on current service dependencies:
rows = [
    ["category", "subcategory", "active", "sort_order"],
    ["Food", "Groceries", "true", "1"],
]
```

**Location:**
- Not detected. No fixture modules, factory helpers, or sample test data files are present.
- Manual live test data is embedded directly in `test_google.py`.
- For future tests, keep static sheet rows in test fixtures and pass them through fake worksheet objects rather than reading from `credentials.json`.

## Coverage

**Requirements:** None enforced.

**View Coverage:**
```bash
# Not available; no coverage tool configured
```

## Test Types

**Unit Tests:**
- Not currently implemented.
- Highest-value unit targets are pure or mostly pure functions:
  - `parse_amount()` and `parse_amount_with_optional_comment()` in `services/expenses.py`
  - `get_current_month_key()` and `_parse_decimal()` in `services/budget.py`
  - `normalize_text()` and `normalize_username()` in `services/google_sheets.py`
  - `add_shopping_item()`, `remove_shopping_items_by_numbers()`, and `clear_shopping_list()` in `services/shopping.py` with mocked worksheets
  - `create_session()`, `get_active_session()`, `pop_session()`, and `is_stale_session()` in `state/expense_session.py` and `state/shopping_session.py`

**Integration Tests:**
- Manual integration testing exists through `test_google.py`.
- `test_google.py` uses real `GOOGLE_CREDENTIALS_FILE` and `SPREADSHEET_ID` names from `secrets.py`, reads the first worksheet, and appends a row.
- No non-destructive integration test harness exists for Google Sheets services.

**E2E Tests:**
- Not used.
- No aiogram bot simulator, Telegram API test harness, browser test, or webapp E2E setup is detected.

## Common Patterns

**Async Testing:**
```python
# No async test pattern exists.
# Handler code is async and awaits aiogram objects:
async def start_shopping_flow(message: types.Message) -> None:
    if not await check_access_message(message):
        return
```

**Error Testing:**
```python
# Current implementation pattern raises ValueError for validation.
try:
    amount = Decimal(normalized)
except InvalidOperation as exc:
    raise ValueError("...") from exc
```

**Manual Smoke Testing:**
```python
# Current executable-script pattern:
if __name__ == "__main__":
    main()
```

**Recommended Placement For New Tests:**
- Add service unit tests for data parsing under `tests/test_expenses_service.py` or equivalent if pytest is introduced.
- Add Google Sheets fake worksheet tests under `tests/test_budget_service.py`, `tests/test_shopping_service.py`, and `tests/test_access_service.py`.
- Add state TTL tests under `tests/test_expense_session.py` and `tests/test_shopping_session.py`.
- Keep `test_google.py` manual-only unless it is rewritten to avoid live data writes and secret-backed credentials.

---

*Testing analysis: 2026-06-29*
