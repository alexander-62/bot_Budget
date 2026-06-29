# Bot Budget

## What This Is

Bot Budget is an existing Telegram bot for personal or household budget tracking. It lets allowed Telegram users view limits, add expenses, inspect recent expenses, and manage a shared shopping list backed by Google Sheets.

The current improvement project keeps Google Sheets as the visible data store, but makes the bot feel faster, safer to change, and easier to use during repeated expense entry.

## Core Value

Users can record expenses in Telegram quickly and reliably without waiting on unnecessary Google Sheets work.

## Requirements

### Validated

- Existing bot starts from `bot.py` / `app.py` and uses aiogram polling.
- Existing access control checks users against the `Users` worksheet.
- Existing users can view limits and category details from Google Sheets.
- Existing users can add expenses through a category, subcategory, amount, and confirmation flow.
- Existing users can view recent expenses from the expenses worksheet.
- Existing users can add, remove, and clear shopping-list items.
- Existing process manager can start, stop, restart, and check the bot process.

### Active

- [ ] Reduce repeated Google Sheets client, spreadsheet, and worksheet lookup overhead.
- [ ] Reduce full-sheet reads in common budget, expense, and shopping-list paths.
- [ ] Keep the asyncio bot responsive while Google Sheets operations are slow.
- [ ] Make expense writes append-safe and able to return enough identity for later edit/delete UX.
- [ ] Add focused automated checks before changing shared service and handler behavior.
- [ ] Improve the add-expense UX by saving by default and offering fast next actions.

### Out of Scope

- Replacing Google Sheets with SQLite or another primary database in this milestone - useful later, but too large for the current optimization pass.
- Rebuilding the static Telegram Web App - the current pain is bot latency and expense-entry friction.
- Changing spreadsheet business schema unless required for safe append/edit/delete behavior.
- Reading or committing local secret values from `secrets.py` or `credentials.json`.

## Context

The codebase is a small Python Telegram bot using aiogram, aiohttp, gspread, in-memory sessions, and Google Sheets as durable storage. The codebase map already identifies the main bottleneck: synchronous gspread calls inside async handlers, repeated spreadsheet opening, repeated worksheet listing, and full-sheet scans for operations that should be cached, appended, or range-limited.

Important current behavior:
- `services/google_sheets.py` creates a gspread service account and opens the spreadsheet on every `get_spreadsheet()` call.
- `find_worksheet_case_insensitive()` calls `spreadsheet.worksheets()` repeatedly.
- `services/budget.py` repeatedly reads categories, limits, and expenses with `get_all_values()`.
- `services/expenses.py` scans the full expenses sheet to find the next row before writing.
- `services/shopping.py` reads and writes shopping entries item by item.
- `handlers/expenses.py` currently requires a separate save/cancel confirmation step after amount entry.

## Constraints

- **Persistence**: Google Sheets remains the current durable store so the user can keep using the existing spreadsheet.
- **Runtime**: The bot is a single asyncio process; blocking gspread calls can delay unrelated Telegram updates.
- **Safety**: Expense and shopping writes should avoid row-allocation races where practical.
- **Secrets**: Do not read, print, or commit secret-bearing files.
- **Compatibility**: Keep existing handler, service, keyboard, and session module boundaries unless a phase explicitly changes them.
- **Scope order**: Performance and safe data operations come before the final UX phase.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Keep Google Sheets for this milestone | The user explicitly said the current database is a Google Sheet and wants acceleration first. | Pending |
| Plan UX autosave as the final phase | The edit/delete UX depends on safer append identity and service behavior. | Pending |
| Add both post-save buttons: same category and different expense | Repeated entry should support fast same-category entry and a fresh category flow. | Pending |
| Use sequential phase execution | The bot is small and many changes touch shared services/handlers. | Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

After each phase transition:
1. Requirements invalidated? Move to Out of Scope with reason.
2. Requirements validated? Move to Validated with phase reference.
3. New requirements emerged? Add to Active.
4. Decisions to log? Add to Key Decisions.
5. "What This Is" still accurate? Update if drifted.

After each milestone:
1. Full review of all sections.
2. Core Value check - still the right priority?
3. Audit Out of Scope - reasons still valid?
4. Update Context with current state.

---
*Last updated: 2026-06-29 after initialization*
