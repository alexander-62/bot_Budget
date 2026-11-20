---
phase: 09-bot-profiles
plan: 01
status: complete
requirements_completed: [PROF-01, PROF-02, PROF-03, DATA-01, DATA-02, AUTH-03]
completed: 2026-10-21
---

# Phase 9 — implemented

Added validated profile registry, serialized atomic updates and encrypted-token rollback on persistence failure; new tokens use typed Windows DPAPI calls and never enter registry/repr. Legacy personal remains synthetic until settings need saving; implicit legacy startup survives malformed registry. Explicit new-profile configuration cannot inherit personal token or spreadsheet; shared Google credential path is an intentional optional fallback.

Currency formatting covers expense cards, recent expenses and digest. Profile timezone drives expense date, budget month and digest. New profiles authorize immutable numeric IDs. Shared schema validation enforces the column positions actually used by services; new expense sheets require comment G and expense_id H.

Verification: final isolated runner passed 89 tests across 21 modules. Profile tests: test_bot_profiles (7), test_profile_runtime (5), test_profile_registry_safety (4), plus existing access, expense, budget and digest regressions. Real DPAPI test used only a generated fake token in a temporary directory. No live financial writes.

Deviation: installed GSD CLI uses legacy syntax; milestone state was reset successfully with `state milestone-switch`. Old phases retained rather than deleted. No new production token or profile was fabricated.
