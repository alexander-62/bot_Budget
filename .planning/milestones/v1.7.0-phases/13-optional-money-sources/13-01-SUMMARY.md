---
phase: 13-optional-money-sources
plan: 01
status: complete
requirements_completed: [SRC-01, SRC-02, SRC-03, SRC-04, SRC-05, SRC-06]
completed: 2026-10-21
---

# Phase 13 result — v1.6.1

Implemented optional per-profile `track_money_source`, strict boolean/default false for old registries, runtime selection and desktop checkbox. Enabled profiles require their own active-source list and expense source column I; disabled profiles keep the old schema and do not query sources. H expense_id stays unchanged. New source values are written as text; old blank rows remain blank.

Telegram entry and same-category repeat ask for source only when enabled. Saved expense editor has a source-only change action; amount/comment updates retain historical source (including blank or inactive), source updates retain amount/comment, and identity checks include source when relevant. Disabling the feature does not erase I. Confirmations and recent-expense views escape source text. Digest grouping is unchanged.

Source picker snapshots have unique callback identities, with identity checks after blocking reads. Review found a refreshed-list index bug: an old button could target a different item after a source disappeared. Fixed by rotating picker identity, deleting prior prompt and rejecting obsolete callbacks before lookup. Regression explicitly covers [Cash, Card] → [Card]. Session IDs now use UUIDs to avoid millisecond collisions. Production per-user concurrency isolation remains in app.create_dispatcher and is regression-tested.

Verification: 109 tests in 25 isolated modules passed, including 11 new flow cases, 6 data cases, 2 real-widget form cases and 1 profile-runtime compatibility case. Publication scanner reports zero findings; git diff --check passes. Windows form screenshot with fake business profile was visually inspected; source checkbox and fixed save/cancel controls fit the scrollable form. Tests use fakes/generated temporary config and no live bot/Sheets calls.

README and GOOGLE_SETUP describe opt-in setup and optional source schema. Runtime version: 1.6.1. Implementation is local; no push, actual business setup, real financial writes or changes to the user AGENTS.md were performed. Next operator step: prepare source Sheet/I header and enable the checkbox for the stopped business profile after delivering the update to its computer.
