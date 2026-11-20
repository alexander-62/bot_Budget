---
gsd_state_version: "1.0"
milestone: v1.8.0
milestone_name: Будущие траты
current_phase: 25
status: completed
last_updated: "2026-11-20T23:19:59.583Z"
last_activity: 2026-11-20
last_activity_desc: Phase 25 complete
state_head: 17185a905352bd90f9bda31a3045e98d732c7556
progress:
  total_phases: 8
  completed_phases: 8
  total_plans: 8
  completed_plans: 8
  percent: 100
---

# Project State

## Current Position

Phase: 25
Plan: 8/8 complete
Status: All phases complete
Last activity: 2026-11-20 — Phase 25 complete

## Implementation

- Phase 18: per-profile flag, panel toggle, shared persistent plans, create/edit/cancel/history and safe Telegram sessions.
- Phase 19: confirmation of actual amount/date/source, persistent payment intent and one atomic Sheets financial batch, no blind retry after unknown outcome.
- Phase 20: creator reminders at 21:30 profile time, day-before/day-of/overdue and Monday undated digest, independent subscription and durable acknowledgement.

- Phases 21–25: snooze reminders, recurring weekly/monthly payments, forecast, corrections and reversal, and operator recovery.

## Verification

243 tests across 43 isolated modules under Xorg dummy. 242 passed and one Windows DPAPI test was skipped. All five follow-up phases passed the GSD plan and verification checks. Automated checks include lost and delayed writes, two concurrent outcomes, and the selected profile lock. Live acceptance remains pending.

## Decisions and Limits

Google Sheets remains the durable store. Feature defaults off. Plans support one-off or recurring payments with full payment confirmation. The existing single-writer process model serializes mutations; concurrent human row moves during payment are outside the Sheets transaction contract. Panel recovery retries the saved payment with a shared Sheets guard. Legacy operations without an actual row remain unresolved. Telegram delivery acknowledgement is at-least-once if persistence fails.

## Delivery Status

Branch: feat/planned-expense-improvements, based on GitHub origin/main 055b906 checked in this session. Implementation commit: 9094b11. GSD phase reports committed separately. No production bot restart or live financial-table write was performed. Deployment and live acceptance of v1.8.0 are tracked separately. Enable the feature for a selected profile from the updated panel after delivery; verify using UAT.md.

Previous v1.7.0 planning snapshots and phases 1–17 are preserved under milestones/. The previous implementation was merged in main; its operator acceptance was not verified here.
