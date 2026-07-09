# Bot Budget

## What This Is

Bot Budget is an existing Telegram bot for personal or household budget tracking. It lets allowed Telegram users view limits, add expenses, inspect recent expenses, and manage a shared shopping list backed by Google Sheets.

The current improvement project keeps Google Sheets as the visible data store, but makes the bot feel faster, safer to change, and easier to use during repeated expense entry.

## Core Value

Users can record expenses in Telegram quickly and reliably, and the household gets a daily reminder with a shared category summary so missed expenses are caught the same evening.

## Requirements

### Validated

- Existing bot starts from `bot.py` / `app.py` and uses aiogram polling.
- Existing access control checks users against the `Users` worksheet.
- Existing users can view limits and category details from Google Sheets.
- Existing users can add expenses through a category, subcategory, and amount flow with autosave and post-save actions.
- Existing users can view recent expenses from the expenses worksheet.
- Existing users can add, remove, and clear shopping-list items.
- Existing enabled users receive an evening reminder with today's shared category totals, including empty-day reminders.
- Existing process manager can start, stop, restart, and check the bot process.
- Bot keeps Google Sheets calls off critical async handler paths.
- Expense writes are append-safe and return saved row identity plus `expense_id`.
- Startup validates config names, credentials path, and required Google Sheets schema.
- Automated tests cover cache behavior, access parsing, expense parsing/write identity, and saved-action flow.
- Runtime smoke check passes under installed dependencies.

### Active
- None for current implementation slice. Phase 8 implementation complete; live rollout requires the `Users` sheet headers.

### Out of Scope

- Replacing Google Sheets with SQLite or another primary database in this milestone - useful later, but too large for the current optimization pass.
- Rebuilding the static Telegram Web App - the current pain is bot latency and expense-entry friction.
- Changing spreadsheet business schema unless required for safe append/edit/delete behavior.
- Reading or committing local secret values from `secrets.py` or `credentials.json`.

## Context

The codebase is a small Python Telegram bot using aiogram, aiohttp, gspread, in-memory sessions, and Google Sheets as durable storage. The codebase map already identifies the main bottleneck: synchronous gspread calls inside async handlers, repeated spreadsheet opening, repeated worksheet listing, and full-sheet scans for operations that should be cached, appended, or range-limited.

Important current behavior:
- `services/google_sheets.py` caches gspread client, spreadsheet, and normalized worksheet lookup results.
- `services/budget.py` shares a short-lived monthly snapshot for limit and category reads.
- `services/expenses.py` appends new expenses, returns `SavedExpense`, and verifies `expense_id` before edit/delete mutations.
- `handlers/expenses.py` autosaves after amount entry and offers edit/repeat/fresh follow-up actions.
- Startup validates required config names, credentials path, and expected Sheets schema before bot polling starts.
- Focused unit tests and runtime smoke checks exist for the milestone's changed paths.

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
| Keep Google Sheets for this milestone | The user explicitly said the current database is a Google Sheet and wants acceleration first. | Complete |
| Plan UX autosave as the final phase | The edit/delete UX depends on safer append identity and service behavior. | Complete |
| Add both post-save buttons: same category and different expense | Repeated entry should support fast same-category entry and a fresh category flow. | Complete |
| Use sequential phase execution | The bot is small and many changes touch shared services/handlers. | Complete |
| Use generated `expense_id` in column `H` for stale-safe edit/delete | Row number alone is not enough when rows can shift. | Complete |
| Configure daily digest recipients only through Google Sheets | The user wants no Telegram settings UI for this feature; `Users` remains the admin-controlled configuration surface. | Complete |

## Phase Notes

- Phase 1 validated cached client, spreadsheet, and worksheet lookup reuse.
- Phase 2 validated shared monthly budget snapshots, bounded recent-expense reads, and batch shopping-list appends.
- Phase 3 validated threaded Sheets access at handler and startup boundaries so the bot loop stays responsive.
- Phase 4 validated append-safe expense writes plus returned saved-record identity.
- Phase 5 validated startup/schema checks, occupied-port diagnostics, and repo ignore rules for duplicates.
- Phase 6 validated fake-based unit coverage and a real smoke check under installed dependencies.
- Phase 7 validated autosave expense entry with edit/repeat/fresh follow-up actions.
- Phase 8 adds the evening digest reminder milestone slice.

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
*Last updated: 2026-07-09 for phase 8 daily digest*
