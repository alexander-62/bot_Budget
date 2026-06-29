---
phase: 2
slug: read-path-optimization
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-29
---

# Phase 2 Validation Strategy

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `unittest` |
| **Quick run command** | `python -m py_compile services\\budget.py services\\expenses.py services\\shopping.py handlers\\shopping.py tests\\test_phase2_read_paths.py` |
| **Full suite command** | `python -m unittest tests.test_google_sheets_cache tests.test_phase2_read_paths` |

## Coverage

| Requirement | Behavior | Test |
|-------------|----------|------|
| PERF-03 | Budget/category views reuse one monthly snapshot | `tests.test_phase2_read_paths.Phase2ReadPathTests.test_budget_views_share_one_snapshot_until_cleared` |
| PERF-04 | Recent expenses reads a bounded tail range | `tests.test_phase2_read_paths.Phase2ReadPathTests.test_recent_expenses_reads_bounded_tail_range` |
| PERF-05 | Shopping-list batch add reads once and appends once | `tests.test_phase2_read_paths.Phase2ReadPathTests.test_shopping_batch_add_reads_once_and_appends_once` |

## Sign-Off

- [x] Automated verification exists for each phase requirement.
- [x] Verification passes in the current workspace.

