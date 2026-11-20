---
gsd_state_version: "1.0"
milestone: v1.8.0
milestone_name: Будущие траты
current_phase: 20
current_phase_name: Напоминания
status: completed
last_updated: "2026-11-20T20:06:08.048Z"
last_activity: 2026-11-20
state_head: d1f2df36472dd0f685b1f1ecfcea446b9b4c2365
progress:
  total_phases: 3
  completed_phases: 3
  total_plans: 3
  completed_plans: 3
  percent: 100
last_activity_desc: Phase 20 complete
---

# Project State

## Current Position

Phase: 20 (Напоминания)
Plan: 3/3 complete
Status: All phases complete
Last activity: 2026-11-20

## Implementation

- Phase 18: per-profile flag, panel toggle, shared persistent plans, create/edit/cancel/history and safe Telegram sessions.
- Phase 19: confirmation of actual amount/date/source, persistent payment intent and one atomic Sheets financial batch, no blind retry after unknown outcome.
- Phase 20: creator reminders at 21:30 profile time, day-before/day-of/overdue and Monday undated digest, independent subscription and durable acknowledgement.

## Verification

228 tests in 39 isolated modules: zero module failures, one Windows DPAPI skip. The 40 new tests pass, including real Tk widgets under Xorg dummy and actual aiogram dispatcher with fake transports. All three GSD plan structures and source-fingerprinted phase verification reports pass. Publication audit has zero findings. Runtime smoke, compilation and whitespace checks pass.

## Decisions and Limits

Google Sheets remains the durable store. Feature defaults off. Plans are one-off/full-payment only. The existing single-writer process model serializes mutations; concurrent human row moves during payment are outside the Sheets transaction contract. A persistently unknown financial outcome stays processing until operator reconciliation. Telegram delivery acknowledgement is at-least-once if persistence fails.

## Delivery Status

Branch: feat/planned-expenses, based on GitHub origin/main 055b906 checked in this session. Implementation commit: 9094b11. GSD phase reports committed separately. No production bot restart or live financial-table write was performed. Publication and deployment of v1.8.0 have not been performed. Enable the feature for a selected profile from the updated panel after delivery; verify using UAT.md.

Previous v1.7.0 planning snapshots and phases 1–17 are preserved under milestones/. The previous implementation was merged in main; its operator acceptance was not verified here.
