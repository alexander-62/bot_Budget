# Phase 8 Summary: Evening Daily Digest

**Status:** complete
**Completed:** 2026-07-09

## Delivered

- Added `services/daily_digest.py` for recipient parsing, category-only daily aggregation, message formatting, and sent-date updates.
- Added `scheduler.py` to run the evening digest loop outside Telegram handlers.
- Wired the scheduler into `app.main` with cancellation during shutdown.
- Added digest constants for enabled/disabled values, send time, timezone, and scheduler interval.
- Updated startup validation to require `digest_enabled` and `last_digest_date` in the `Users` worksheet.
- Added focused fake-based tests in `tests/test_daily_digest.py`.
- Stabilized two existing tests:
  - phase 2 budget read-path test no longer depends on the real current month;
  - phase 7 keyboard fake now accepts existing `style=` kwargs.

## Runtime Behavior

- Recipients come from `Users`.
- Blank `digest_enabled` means enabled.
- Explicit disabled values skip a recipient.
- Digest content includes all expenses recorded today, grouped by category only.
- If there are no expenses today, the bot still sends a reminder.
- After each successful send, `last_digest_date` is updated for that recipient.
- Telegram settings UI was not added.

## Rollout Note

The live `Users` sheet must include these headers before startup validation will pass:

- `digest_enabled`
- `last_digest_date`
