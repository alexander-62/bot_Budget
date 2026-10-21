---
gsd_state_version: 1.0
milestone: v1.6.0
milestone_name: Multiple Budget Bots
status: implementation_complete
last_updated: "2026-10-21T15:14:29.102Z"
last_activity: 2026-10-21 - Phase 14 complete; v1.6.2 per-bot panel pictures; tests passed.
progress:
  total_phases: 6
  completed_phases: 6
  total_plans: 6
  completed_plans: 6
  percent: 100
---

# Project State: Bot Budget

## Current Position

Phase: 14 - Per-bot profile pictures complete
Plan: 14-01 complete
Status: Implementation complete; remote update and real business setup pending
Last activity: 2026-10-21 - Panel pictures v1.6.2; 122 tests/27 modules plus final 18 UI checks passed.

## Project Reference

See PROJECT.md and ROADMAP.md. Active milestone phases 9-14 have PLAN, SUMMARY and passed VERIFICATION files. Phases 1-8 remain history.

## Phase Status

| Phase | Status | Requirements |
|---|---|---|
| 9. Bot Profiles | Complete | PROF-01/02/03, DATA-01/02, AUTH-03 |
| 10. Profile Processes | Complete | PROC-01/02/03 |
| 11. Multi-Bot Panel | Complete | UI-01/02/03/04 |
| 12. Platform Verification | Complete | TEST-05, DOC-01 |
| 13. Optional Money Sources | Complete | SRC-01/02/03/04/05/06 |
| 14. Per-Bot Profile Pictures | Complete | IMG-01/02/03/04 |

## Next Action

Operator opens `bot.bat ui`, adds new business token and dedicated Sheet, selects RUB, validates and starts the profile. Verify /start and first expense with allowed user IDs. Existing personal data and local secrets were not modified by the implementation. No actual business deployment is claimed.

## Decisions and Verification

- Common code, one process and spreadsheet per profile; single global panel/tray.
- Windows DPAPI protects new tokens; legacy personal config preserved.
- New profiles authorize numerical IDs; visibility shared within each bot.
- Isolated full suite passes 109 tests; fake two-worker integration and legacy v1.5 personal migration covered.
- Panel/form screenshots checked using scoped window HWND capture; no real credentials in screenshots.
- Installed SDK uses legacy CLI syntax; state milestone switch succeeded. Final state written atomically with matching frontmatter/body, preserving historical notes below.
- No push, live service calls, financial writes or Windows-login changes were performed.

## Historical Notes

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

## Roadmap Evolution

- 2026-10-21: Phase 13 added via GSD SDK phase add at explicit user request; planned and implemented autonomously.
- Optional money-source tracking shipped locally in v1.6.1, default disabled. H identity and prior expense data preserved, I source opt-in.
- For business after remote delivery: prepare source Sheet and I header; stop profile, enable checkbox, validate/save, restart. Personal requires no table changes.
- No GitHub push, production profile changes, live bot calls or financial writes were performed. User AGENTS.md edits remain uncommitted.

## Phase 14 follow-up

- Added via GSD phase add; user confirmed pictures only in panel. Completed select/reset, managed assets and safe profile routing.
- Phase 13 already committed at 16dd16f; picture feature saved separately. No actual image/profile/API changes or GitHub push.
- Next: after remote update, choose each image from its profile card on the panel computer.
