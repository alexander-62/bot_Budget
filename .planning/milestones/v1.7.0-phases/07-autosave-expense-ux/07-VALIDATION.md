---
phase: 7
slug: autosave-expense-ux
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-29
---

# Phase 7 Validation Strategy

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `unittest` / syntax validation |
| **Quick run command** | `python -m py_compile handlers\\expenses.py keyboards\\expenses.py services\\expenses.py state\\expense_session.py` |
| **Full suite command** | Focused phase 7 tests plus shared suite from phase 6 |

## Coverage

| Requirement | Behavior | Test |
|-------------|----------|------|
| UX-01 | Amount entry autosaves | Handler/service tests |
| UX-02 | Post-save summary includes edit action | Keyboard/handler tests |
| UX-03 | Same-category repeat works | Saved-action flow tests |
| UX-04 | Fresh-expense restart works | Saved-action flow tests |
| UX-05 | Edit/delete reject stale callbacks safely | Identity-verification tests |

## Sign-Off

- [x] Autosave flow enabled.
- [x] Post-save action keyboard added.
- [x] Edit/delete guarded by saved identity.
- [x] Focused tests added.
