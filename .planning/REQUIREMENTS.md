# Requirements: Bot Budget Optimization

**Defined:** 2026-06-29
**Core Value:** Users can record expenses in Telegram quickly and reliably without waiting on unnecessary Google Sheets work.

## v1 Requirements

### Google Sheets Performance

- [ ] **PERF-01**: Bot reuses a cached gspread client and spreadsheet object instead of creating them for every service call.
- [ ] **PERF-02**: Bot reuses worksheet lookups by normalized worksheet name instead of listing all worksheets on every operation.
- [x] **PERF-03**: Budget limit and category views share parsed Google Sheets data within a short-lived cache or request snapshot.
- [x] **PERF-04**: Recent-expenses retrieval avoids unnecessary full-sheet processing when a bounded recent range or cache is sufficient.
- [x] **PERF-05**: Shopping-list batch add reads existing items once and writes new items in a batch where possible.

### Async Responsiveness

- [ ] **ASYNC-01**: Blocking Google Sheets service calls are moved behind a clear async boundary so slow Sheets requests do not block unrelated Telegram updates.
- [ ] **ASYNC-02**: Handlers keep Telegram responses and callback acknowledgements responsive while service operations run.
- [ ] **ASYNC-03**: Slow startup notification work no longer blocks bot readiness longer than necessary.

### Expense Write Safety

- [ ] **EXP-01**: Expense creation uses append semantics or another race-resistant write path instead of scanning the full sheet to compute the next row.
- [ ] **EXP-02**: Expense write returns enough saved-record identity for later post-save actions such as edit or delete.
- [ ] **EXP-03**: Expense parsing with optional comment remains compatible with existing user input formats.

### Reliability and Operations

- [ ] **OPS-01**: Startup fails with actionable configuration errors when required non-secret config names or Google Sheets schema are missing.
- [ ] **OPS-02**: Bot process management avoids common double-start or occupied-port confusion.
- [ ] **OPS-03**: Duplicate and backup files are either removed from the active code path or explicitly ignored so future edits target authoritative files.

### Test and Review Coverage

- [ ] **TEST-01**: Automated tests cover amount parsing, optional comments, and money formatting edge cases.
- [ ] **TEST-02**: Automated tests cover access normalization and malformed `Users` worksheet rows using mocks/fakes.
- [ ] **TEST-03**: Automated tests cover Google Sheets adapter caching and service behavior without reading real secrets.
- [ ] **TEST-04**: A smoke check imports the app, builds keyboards, and creates the dispatcher under installed dependencies.

### Expense Entry UX

- [ ] **UX-01**: After amount entry, the bot saves the expense by default without asking for a separate "Save / Cancel" confirmation.
- [ ] **UX-02**: The post-save message shows a concise saved-expense summary and an "Изменить" action.
- [ ] **UX-03**: The post-save message provides "Добавить ещё в эту категорию" to enter another amount using the same category and subcategory context.
- [ ] **UX-04**: The post-save message provides "Добавить другую трату" to start a fresh expense flow from category selection.
- [ ] **UX-05**: Edit/delete behavior is safe against stale callbacks and does not corrupt later expenses.

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
| PERF-01 | Phase 1 | Pending |
| PERF-02 | Phase 1 | Pending |
| PERF-03 | Phase 2 | Complete |
| PERF-04 | Phase 2 | Complete |
| PERF-05 | Phase 2 | Complete |
| ASYNC-01 | Phase 3 | Pending |
| ASYNC-02 | Phase 3 | Pending |
| ASYNC-03 | Phase 3 | Pending |
| EXP-01 | Phase 4 | Pending |
| EXP-02 | Phase 4 | Pending |
| EXP-03 | Phase 4 | Pending |
| OPS-01 | Phase 5 | Pending |
| OPS-02 | Phase 5 | Pending |
| OPS-03 | Phase 5 | Pending |
| TEST-01 | Phase 6 | Pending |
| TEST-02 | Phase 6 | Pending |
| TEST-03 | Phase 6 | Pending |
| TEST-04 | Phase 6 | Pending |
| UX-01 | Phase 7 | Pending |
| UX-02 | Phase 7 | Pending |
| UX-03 | Phase 7 | Pending |
| UX-04 | Phase 7 | Pending |
| UX-05 | Phase 7 | Pending |

**Coverage:**
- v1 requirements: 23 total
- Mapped to phases: 23
- Unmapped: 0

---
*Requirements defined: 2026-06-29*
*Last updated: 2026-06-29 after phase 2*
