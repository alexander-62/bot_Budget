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


## v1.7.0 Budget settings — implementation complete, 2026-10-22

Phases 15–17 implemented and verified (180 tests, 33 modules; one Windows DPAPI skip). Source is in main at 50a4ec2, followed by 055b906. Live migration and operator Telegram acceptance were not verified here and remain rollout tasks. Planning snapshots archived under milestones/v1.7.0-*.md.

## v1.8.0 Будущие траты — implementation complete, 2026-11-20

Phases 18–20 and all 13 requirements are implemented and locally verified on feat/planned-expenses. Runtime 1.8.0. Evidence: 228 tests / 39 modules, zero module failures, one Windows DPAPI skip; 40 new tests. GSD plan validators and fingerprinted phase reports pass. Publication and deployment have not been performed; UAT.md tracks live operator acceptance. Feature is disabled by default, one-off/full-payment only.

### v1.8.0 follow-up phases 21–25

Added snooze, recurring plans, forecast, payment correction, and panel recovery. Local validation finished with 242 passes and one Windows DPAPI skip across 43 modules.
