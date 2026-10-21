# Milestones

## Previous implementation — through runtime v1.5.0

Phases 1–8 delivered Sheets caching/read optimization, async boundaries, safe writes, tests, autosave and daily digest. Runtime v1.5.0 added the Windows control panel and single-instance protection outside the earlier phase numbering. Original phase files remain in `.planning/phases/01-*` through `08-*`; original requirements and roadmap are archived in `milestones/` before updating the active milestone. The old daily-digest live-sheet header rollout was not verified in this session.

## v1.6.0 Multiple Budget Bots — in progress, 2026-10-21

User-approved scope: general profile support, independent budget bots, RUB business budget, existing EUR personal compatibility, a shared Windows panel with add/connect/manage and selective autostart. Phases 9–12 continue numbering. Live onboarding needs the business bot token, dedicated Sheet and user IDs supplied by the operator through the panel.

Implementation phases 9?12 verified with 89 tests in 21 modules and zero publication findings. Actual business onboarding remains pending operator token/table.

## Phase 13 follow-up - runtime v1.6.1, 2026-10-21

Optional money sources implemented and verified: per-profile boolean, active own-sheet sources, column I persistence, safe entry/edit/recent views and desktop toggle. 109 tests/25 modules pass, publication findings 0. Remote rollout and real business configuration remain operator actions.

## Phase 14 follow-up - runtime v1.6.2, 2026-10-21

Independent panel pictures implemented and verified: managed local imports, select/reset, metadata-only persistence and safe profile routing. Scope explicitly panel only. 122 tests/27 modules pass plus final 18 affected UI regressions, zero publication findings. Separate commit from phase13; remote deployment pending.
