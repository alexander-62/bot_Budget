# Phase 8 Context: Evening Daily Digest

**Date:** 2026-07-09
**Mode:** mvp

## User Intent

Send an evening reminder to every enabled bot user. The message should contain all expenses recorded today across all users, grouped only by category. If no expenses were recorded, the bot should still send a reminder asking whether anything was forgotten.

The user explicitly does not want Telegram UI settings for this feature. Recipient configuration should live in Google Sheets, with local/code configuration only for global runtime settings such as send time.

## Decisions

- Use `Users` as the recipient configuration source.
- Add `digest_enabled` and `last_digest_date` to the `Users` worksheet contract.
- Treat empty `digest_enabled` as enabled by default.
- Disable only on explicit false-like values: `FALSE`, `0`, `no`, `нет`, `выкл`, `выключено`.
- Digest content is shared for the household/team: no per-user filtering and no subcategory breakdown.
- Keep scheduling outside handlers and run blocking Sheets calls via the existing async boundary.

## Relevant Architecture

- `app.py` owns runtime startup and background tasks.
- `services/access.py` already reads `Users` and syncs chat ids, but digest-specific recipient rules should stay in a separate service.
- `services/expenses.py` owns expense writes and recent-expense UI reads; digest aggregation should be a separate read model over the expenses worksheet.
- `services/async_tools.py` provides the existing `run_blocking` async boundary.

## Verification Focus

- Recipient parsing with blank enabled values and explicit disabled values.
- Category-only aggregation for all users' expenses on a date.
- Empty-day reminder formatting.
- Startup schema validation for the new `Users` columns.
- No live Google Sheets calls in tests.
