# Roadmap: Bot Budget Optimization

**Created:** 2026-06-29
**Mode:** Sequential
**Granularity:** Standard

## Overview

This roadmap improves the existing Google Sheets-backed Telegram budget bot in risk order. The first milestone reduced avoidable Sheets overhead, made blocking I/O safer for the async bot, prepared expense writes for post-save actions, added tests and operational guardrails, and shipped autosave expense entry.

Phase 8 added an evening daily digest reminder: a shared category-level summary of today's expenses is sent to every enabled user, and an empty-day reminder still prompts the household to record missed expenses.

## Phases

### Phase 1: Spreadsheet Adapter Cache

**Goal:** Centralize and cache Google Sheets client, spreadsheet, and worksheet lookup behavior.
**Mode:** mvp

**Requirements:** PERF-01, PERF-02

**Success Criteria:**
1. `services/google_sheets.py` reuses a cached service-account client and spreadsheet object.
2. Worksheet lookup by configured sheet name avoids repeated full worksheet listing for common paths.
3. Cache invalidation or reset behavior exists for tests and recovery.
4. Existing access, budget, expense, and shopping services continue to call the central adapter.

**Notes:**
- Do not read or expose `secrets.py` or `credentials.json`.
- Keep public service APIs stable unless the next phase needs a signature change.

### Phase 2: Read Path Optimization

**Goal:** Reduce repeated full-sheet reads in budget, recent-expense, and shopping-list operations.
**Mode:** mvp
**Status:** complete

**Requirements:** PERF-03, PERF-04, PERF-05

**Success Criteria:**
1. Budget views share a short-lived monthly snapshot for categories, limits, and spent totals.
2. Category card generation does not reread the same worksheets multiple times in one user action.
3. Recent expenses reads a bounded tail range or uses a lightweight cache where practical.
4. Adding several shopping items reads existing entries once and writes new rows in one batch where the Sheets API supports it.
5. Cache TTLs are documented and can be bypassed/refreshed after writes.

**Notes:**
- Avoid overbuilding a generic repository layer until the bottlenecks are measured or obvious.
- Preserve existing sheet layout.

### Phase 3: Async Responsiveness Boundary

**Goal:** Prevent slow gspread calls from blocking the bot event loop.
**Mode:** mvp
**Status:** complete

**Requirements:** ASYNC-01, ASYNC-02, ASYNC-03

**Success Criteria:**
1. Handlers call blocking Sheets-backed service work through a clear async helper, such as `asyncio.to_thread` or a bounded executor.
2. Callback handlers acknowledge user actions promptly where Telegram expects fast feedback.
3. Startup notification work no longer delays polling startup unnecessarily.
4. Errors from threaded service calls are still logged and translated into user-facing retry messages.

**Notes:**
- Keep the sync service layer if that minimizes churn; wrap it at the handler boundary.
- Use a bounded approach if concurrent Sheets calls become a quota risk.

### Phase 4: Append-Safe Expense Writes

**Goal:** Make expense creation race-resistant and return saved-record identity for future UX actions.
**Mode:** mvp
**Status:** complete

**Requirements:** EXP-01, EXP-02, EXP-03

**Success Criteria:**
1. `write_expense` no longer scans the full expenses sheet solely to compute the next row.
2. Expense creation uses append semantics or an equivalent safe write path.
3. The write function returns a structured saved expense result, including enough identity for edit/delete actions.
4. Amount parsing and optional inline comments keep existing behavior.
5. Existing confirmation flow still works after the service change.

**Notes:**
- This phase is the prerequisite for the later UX phase.
- If Google Sheets cannot reliably return row identity from append, add a generated expense id column or another deterministic identity strategy.

### Phase 5: Operational Reliability Cleanup

**Goal:** Make runtime failures and repository structure easier to understand before larger UX changes.
**Mode:** mvp
**Status:** complete

**Requirements:** OPS-01, OPS-02, OPS-03

**Success Criteria:**
1. Startup validates required config names and required worksheets/headers with actionable errors.
2. Double-start or occupied Web App port scenarios are detected or explained clearly.
3. Duplicate and backup source files are removed from version control or ignored after confirming they are not authoritative.
4. README or operational docs reflect the current start/stop/status workflow.

**Notes:**
- Treat deletion of duplicate files carefully; do not remove user data or secret files.
- Keep this phase focused on reliability, not a deployment redesign.

### Phase 6: Test Harness and Quality Gate

**Goal:** Add enough automated coverage to safely change expense, access, and Sheets adapter behavior.
**Mode:** mvp
**Status:** complete

**Requirements:** TEST-01, TEST-02, TEST-03, TEST-04

**Success Criteria:**
1. Tests cover amount parsing, optional comments, decimal rounding, and invalid input.
2. Tests cover username normalization, empty username behavior, malformed user rows, and cache behavior with fakes.
3. Tests cover adapter caching and service behavior without contacting real Google APIs.
4. A smoke check imports the application modules, builds keyboards, and creates the dispatcher.
5. Test command is documented and can run without reading secret files.

**Notes:**
- Prefer mocks/fakes over live Google Sheets tests.
- Keep `test_google.py` as a manual integration probe unless explicitly replacing it.

### Phase 7: Autosave Expense UX

**Goal:** Remove the extra save-confirmation click and offer fast post-save actions.
**Mode:** mvp
**Status:** complete

**Requirements:** UX-01, UX-02, UX-03, UX-04, UX-05

**Success Criteria:**
1. After a user enters amount/comment, the bot saves the expense by default.
2. The bot sends a concise saved-expense summary with an "Изменить" button.
3. The same post-save keyboard includes "Добавить ещё в эту категорию".
4. The same post-save keyboard includes "Добавить другую трату".
5. "Добавить ещё в эту категорию" starts the amount step with the same category/subcategory.
6. "Добавить другую трату" starts a fresh category-selection flow.
7. Edit/delete behavior uses the saved-record identity from Phase 4 and rejects stale callbacks safely.

**Notes:**
- Keep this phase last because the UX depends on reliable saved expense identity.
- If full edit/delete is too risky in one pass, ship autosave plus next-action buttons first and keep edit as a guarded follow-up inside the phase plan.

### Phase 8: Evening Daily Digest

**Goal:** Send an evening reminder with today's shared expense totals grouped by category to every enabled recipient.
**Mode:** mvp
**Status:** complete

**Requirements:** DIGEST-01, DIGEST-02, DIGEST-03, DIGEST-04, DIGEST-05, DIGEST-06

**Success Criteria:**
1. Recipients are read from `Users` rows with valid `chat_id/user_id`.
2. `digest_enabled` defaults to enabled when blank and disables only on explicit false-like values.
3. The daily digest reads all expenses for the current day and groups totals by category only.
4. Users receive a reminder even when today's expense list is empty.
5. Successful sends write `last_digest_date` for each recipient and avoid duplicate same-day sends.
6. The feature adds no Telegram settings UI.
7. Tests cover recipient parsing, category aggregation, empty-day message formatting, and no live Google Sheets calls.

**Notes:**
- Required `Users` headers for the digest are `digest_enabled` and `last_digest_date`.
- Keep scheduler work outside Telegram handlers and run blocking Sheets calls through the async boundary.

## Next Step

Phase 8 complete. Next step is runtime rollout: add the `digest_enabled` and `last_digest_date` headers to the live `Users` sheet, restart the bot, and observe the first evening send.
