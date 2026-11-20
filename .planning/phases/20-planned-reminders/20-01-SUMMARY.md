---
phase: 20-planned-reminders
plan: 01
subsystem: budget
status: complete
completed: 2026-11-20
requirements-completed: [REM-01, REM-02, REM-03, REM-04]
tech-stack:
  added: []
  patterns: [profile-feature-flag, stable-record-identity, sheets-atomic-batch]
key-files:
  created: [scheduler.py, services/planned_reminders.py, services/planned_expenses.py, handlers/planned.py, state/planned_session.py, README.md, tests/planned_fakes.py, tests/test_planned_reminders.py, tests/test_planned_flow.py]
key-decisions:
  - "Single process per budget; synchronous Sheets mutations are serialized behind run_blocking."
  - "No live financial writes for verification; operator rollout is separate."
---

# Phase 20: Напоминания — Summary

## Accomplishments

- Day-before/day-of/overdue and weekly-undated schedules in profile time. Evidence: `tests/test_planned_reminders.py`.
- Independent subscription, persisted delivery buckets and isolated scheduler failures. Evidence: `tests/test_planned_reminders.py`.
- Persisted-ID reminder callbacks reopen current cards after restart. Evidence: `tests/test_planned_flow.py`.

## Task Commits

Integrated production implementation: `9094b11` (`feat: add planned expenses with atomic payments and independent reminders`). The three plans share service/handler endpoints and were committed together after their focused checks; their verification and traceability remain separate.

## Validation Evidence

`DISPLAY=:93 .venv/bin/python scripts/run_tests.py`: 228 tests in 39 isolated modules, zero failed modules; one Windows DPAPI skip. All 40 new future-payment tests passed, including real Tk panel interaction under Xorg dummy and real aiogram dispatcher routing with fake external I/O. Runtime smoke and compile checks passed. Publication audit: zero findings. Plan structure validated through installed GSD CLI without errors/warnings.

## Decisions and Deviations

- User authorized autonomous execution; existing agreed MVP supplied locked decisions. Existing stack was reused and broad ecosystem research skipped per project configuration.
- Execution and review were inline; no subagents were requested. Windows DPAPI and live Telegram/Sheets acceptance are not claimed as tested.
- A durable `processing` intent precedes the atomic financial batch. Unknown network outcomes block a second append even while the first request may still be in flight; definite Sheets rejections permit a fresh confirmation. Persistently unknown outcomes require operator reconciliation, documented in README.
- Existing system had Xorg dummy, which provided a working test display; no system package installation was needed.

## Next Phase Readiness

Automated phase goal verified. Remaining real-computer/Telegram acceptance is tracked in `.planning/UAT.md`; no production restart or live financial write occurred.

## Self-Check: PASSED

All required implementation and test files exist. The production commit is present. Automated behavioral checks pass.
