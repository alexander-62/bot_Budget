---
phase: 4
slug: append-safe-expense-writes
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-29
---

# Phase 4 Validation Strategy

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `unittest` / direct syntax validation |
| **Quick run command** | `python -m py_compile services\\expenses.py handlers\\expenses.py` |
| **Full suite command** | Deferred to phase 6 test harness work |

## Coverage

| Requirement | Behavior | Test |
|-------------|----------|------|
| EXP-01 | Expense creation uses append semantics instead of next-row scanning | Service implementation review in `services/expenses.py` |
| EXP-02 | Expense writes return saved-row identity | `SavedExpense` return value from `write_expense()` |
| EXP-03 | Optional inline comments remain supported | Existing parse helper retained unchanged |

## Sign-Off

- [x] Expense writes now use append semantics.
- [x] Saved expense identity is returned from the write path.
- [x] Syntax check passed in the current workspace.
