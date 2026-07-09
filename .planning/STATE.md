# Project State: Bot Budget

**Initialized:** 2026-06-29
**Current Phase:** Phase 8 - Evening Daily Digest
**Status:** Complete; pending live sheet header rollout

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-06-29)

**Core value:** Users can record expenses in Telegram quickly and reliably, and the household gets a daily reminder with a shared category summary so missed expenses are caught the same evening.
**Current focus:** Roll out the evening daily digest by adding the required `Users` sheet headers and restarting the bot.

## Phase Status

| Phase | Status | Requirements |
|-------|--------|--------------|
| 1. Spreadsheet Adapter Cache | Complete | PERF-01, PERF-02 |
| 2. Read Path Optimization | Complete | PERF-03, PERF-04, PERF-05 |
| 3. Async Responsiveness Boundary | Complete | ASYNC-01, ASYNC-02, ASYNC-03 |
| 4. Append-Safe Expense Writes | Complete | EXP-01, EXP-02, EXP-03 |
| 5. Operational Reliability Cleanup | Complete | OPS-01, OPS-02, OPS-03 |
| 6. Test Harness and Quality Gate | Complete | TEST-01, TEST-02, TEST-03, TEST-04 |
| 7. Autosave Expense UX | Complete | UX-01, UX-02, UX-03, UX-04, UX-05 |
| 8. Evening Daily Digest | Complete | DIGEST-01, DIGEST-02, DIGEST-03, DIGEST-04, DIGEST-05, DIGEST-06 |

## Notes

- Existing `.planning/codebase/` map is available and should be read before implementation phases.
- Phase 4 added append-safe writes plus saved row identity and `expense_id` verification.
- Phase 5 added startup/schema validation and clearer local process diagnostics.
- Phase 6 added focused tests plus real smoke verification in `.venv`.
- Phase 7 enabled autosave expense entry with edit/repeat/fresh next actions.
- 2026-06-29: Restored inline keyboard `style=` hints in `keyboards/expenses.py`, `keyboards/limits.py`, and `keyboards/shopping.py` so Telegram can render the previous colored button style again.
- 2026-06-29: Remote restart now fetches `origin/main` and switches to local `main` automatically before pulling updates.
- 2026-06-29: `update_bot.bat` now fetches origin/main and auto-switches or creates local `main` before pulling updates.
- 2026-06-29: Remote restart now launches a delayed helper process that starts `manage_bot.py start` after the update, instead of relying on `os.execv` in the live bot process.
- 2026-06-29: Remote restart now writes a restart marker and the next bot start sends an explicit "Бот снова запущен" message before polling.
- 2026-07-09: Started Phase 8 evening daily digest as a new milestone slice. Digest recipients are configured only in the `Users` sheet.
- 2026-07-09: Completed Phase 8 implementation and tests. Live rollout requires `digest_enabled` and `last_digest_date` headers in `Users`.
