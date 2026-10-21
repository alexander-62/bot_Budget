# Requirements: Bot Budget Optimization

**Defined:** 2026-06-29
**Core Value:** Users can record expenses in Telegram quickly and reliably, and the household gets a daily reminder with a shared category summary so missed expenses are caught the same evening.

## v1 Requirements

### Google Sheets Performance

- [x] **PERF-01**: Bot reuses a cached gspread client and spreadsheet object instead of creating them for every service call.
- [x] **PERF-02**: Bot reuses worksheet lookups by normalized worksheet name instead of listing all worksheets on every operation.
- [x] **PERF-03**: Budget limit and category views share parsed Google Sheets data within a short-lived cache or request snapshot.
- [x] **PERF-04**: Recent-expenses retrieval avoids unnecessary full-sheet processing when a bounded recent range or cache is sufficient.
- [x] **PERF-05**: Shopping-list batch add reads existing items once and writes new items in a batch where possible.

### Async Responsiveness

- [x] **ASYNC-01**: Blocking Google Sheets service calls are moved behind a clear async boundary so slow Sheets requests do not block unrelated Telegram updates.
- [x] **ASYNC-02**: Handlers keep Telegram responses and callback acknowledgements responsive while service operations run.
- [x] **ASYNC-03**: Slow startup notification work no longer blocks bot readiness longer than necessary.

### Expense Write Safety

- [x] **EXP-01**: Expense creation uses append semantics or another race-resistant write path instead of scanning the full sheet to compute the next row.
- [x] **EXP-02**: Expense write returns enough saved-record identity for later post-save actions such as edit or delete.
- [x] **EXP-03**: Expense parsing with optional comment remains compatible with existing user input formats.

### Reliability and Operations

- [x] **OPS-01**: Startup fails with actionable configuration errors when required non-secret config names or Google Sheets schema are missing.
- [x] **OPS-02**: Bot process management avoids common double-start or occupied-port confusion.
- [x] **OPS-03**: Duplicate and backup files are either removed from the active code path or explicitly ignored so future edits target authoritative files.

### Test and Review Coverage

- [x] **TEST-01**: Automated tests cover amount parsing, optional comments, and money formatting edge cases.
- [x] **TEST-02**: Automated tests cover access normalization and malformed `Users` worksheet rows using mocks/fakes.
- [x] **TEST-03**: Automated tests cover Google Sheets adapter caching and service behavior without reading real secrets.
- [x] **TEST-04**: A smoke check imports the app, builds keyboards, and creates the dispatcher under installed dependencies.

### Expense Entry UX

- [x] **UX-01**: After amount entry, the bot saves the expense by default without asking for a separate "Save / Cancel" confirmation.
- [x] **UX-02**: The post-save message shows a concise saved-expense summary and an "Изменить" action.
- [x] **UX-03**: The post-save message provides "Добавить ещё в эту категорию" to enter another amount using the same category and subcategory context.
- [x] **UX-04**: The post-save message provides "Добавить другую трату" to start a fresh expense flow from category selection.
- [x] **UX-05**: Edit/delete behavior is safe against stale callbacks and does not corrupt later expenses.

### Daily Digest Reminder

- [x] **DIGEST-01**: Bot sends an evening digest to every `Users` row with a valid `chat_id/user_id` unless `digest_enabled` is explicitly disabled.
- [x] **DIGEST-02**: Empty `digest_enabled` means enabled by default; explicit disabled values include `FALSE`, `0`, `no`, `нет`, `выкл`, and `выключено`.
- [x] **DIGEST-03**: Digest content is the shared total of all expenses recorded for the current day, grouped only by category and not split by user or subcategory.
- [x] **DIGEST-04**: Bot still sends the evening reminder when no expenses were recorded today.
- [x] **DIGEST-05**: Successful sends update `last_digest_date` per recipient so restart or repeated scheduler checks do not duplicate the same day's digest.
- [x] **DIGEST-06**: No Telegram settings UI is added for digest configuration; recipient control remains in Google Sheets and global timing remains in code/config.

## v2 Requirements

### Database Evolution

- **DB-01**: Bot can use SQLite or another local database as the primary write store and sync summary views to Google Sheets.
- **DB-02**: Bot can migrate existing Google Sheets data into the new storage layer.

### Access Control

- **AUTH-01**: Bot authorizes primarily by immutable Telegram user id and uses username only for display/onboarding.
- **AUTH-02**: Admin-only operations such as restart are separated from general allowed users.

### Web App

- **WEB-01**: Telegram Web App becomes an interactive expense-entry surface if the chat UX is no longer sufficient.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Full database replacement in v1 | Performance can be improved substantially while keeping Google Sheets. |
| Public deployment/webhook migration | Current bot uses local polling and the requested problem is latency/UX. |
| Secret management migration | Important but separate from the current performance and expense-entry flow. |
| Redesigning all bot copy | Only the add-expense UX is in scope for this milestone. |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PERF-01 | Phase 1 | Complete |
| PERF-02 | Phase 1 | Complete |
| PERF-03 | Phase 2 | Complete |
| PERF-04 | Phase 2 | Complete |
| PERF-05 | Phase 2 | Complete |
| ASYNC-01 | Phase 3 | Complete |
| ASYNC-02 | Phase 3 | Complete |
| ASYNC-03 | Phase 3 | Complete |
| EXP-01 | Phase 4 | Complete |
| EXP-02 | Phase 4 | Complete |
| EXP-03 | Phase 4 | Complete |
| OPS-01 | Phase 5 | Complete |
| OPS-02 | Phase 5 | Complete |
| OPS-03 | Phase 5 | Complete |
| TEST-01 | Phase 6 | Complete |
| TEST-02 | Phase 6 | Complete |
| TEST-03 | Phase 6 | Complete |
| TEST-04 | Phase 6 | Complete |
| UX-01 | Phase 7 | Complete |
| UX-02 | Phase 7 | Complete |
| UX-03 | Phase 7 | Complete |
| UX-04 | Phase 7 | Complete |
| UX-05 | Phase 7 | Complete |
| DIGEST-01 | Phase 8 | Complete |
| DIGEST-02 | Phase 8 | Complete |
| DIGEST-03 | Phase 8 | Complete |
| DIGEST-04 | Phase 8 | Complete |
| DIGEST-05 | Phase 8 | Complete |
| DIGEST-06 | Phase 8 | Complete |

**Coverage:**
- v1 requirements: 29 total
- Mapped to phases: 29
- Unmapped: 0

---
*Requirements defined: 2026-06-29*
*Last updated: 2026-07-09 for phase 8 daily digest*
