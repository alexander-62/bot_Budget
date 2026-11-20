---
phase: 11-multi-bot-panel
plan: 01
status: complete
requirements_completed: [UI-01, UI-02, UI-03, UI-04]
completed: 2026-10-21
---

# Phase 11 — implemented

Added profile picker and cached state badges, selected management/log/table actions, per-profile autostart and add/edit form. Form uses labeled fields, blank masked token on edit and scrollable layout. Telegram getMe and explicit uncached Sheets validation run in workers without leaking transport exceptions. Validation preserves the active runtime's Sheets cache. Save checks process state again while holding runtime/start locks. Cancellation and profile generation guards prevent stale background results from changing another selection.

Verification: seven profile-UI tests, four validation tests, one Sheets-cache isolation test and existing desktop-UI tests pass. Third profile uses the same flow. Windows HWND-scoped screenshots of the panel and empty form were visually inspected: controls/labels fit and no overlaps were observed. Screenshots are local ignored artifacts. Fake states only; network onboarding was not invoked.
