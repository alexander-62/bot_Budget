# Phase 8 Plan: Evening Daily Digest

## Goal

Implement a scheduled evening digest that sends today's shared expense totals by category to every enabled recipient and still sends a reminder when no expenses were recorded.

## Tasks

1. Add digest configuration constants for send time, timezone, check interval, and enabled/disabled value parsing.
2. Add a daily digest service that:
   - reads recipients from `Users`;
   - treats blank `digest_enabled` as enabled;
   - reads `last_digest_date`;
   - updates `last_digest_date` after successful send;
   - reads expenses for a target date;
   - groups by category only;
   - formats non-empty and empty-day messages.
3. Add a scheduler module that:
   - checks whether the global digest time has passed;
   - skips recipients already sent today;
   - sends one shared message to every due recipient;
   - logs per-recipient failures without stopping the loop.
4. Wire scheduler startup and cancellation into `app.main`.
5. Update startup validation to require `digest_enabled` and `last_digest_date` headers in `Users`.
6. Add fake-based tests for recipient parsing, sent-date updates, aggregation, and empty-day formatting.

## Risks

- The live `Users` sheet must add `digest_enabled` and `last_digest_date` before startup validation will pass.
- Google Sheets date formatting can vary; support both `YYYY-MM-DD` and common `DD.MM.YY/YYYY` forms.
- If Telegram send succeeds but updating `last_digest_date` fails, a later retry may duplicate that user's message.

## Acceptance Criteria

- All DIGEST requirements are implemented.
- Unit tests pass without local secrets.
- Existing smoke/import checks still pass or skip only for missing installed dependencies.
