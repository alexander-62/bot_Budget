---
phase: 5
slug: operational-reliability-cleanup
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-29
---

# Phase 5 Validation Strategy

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `unittest` / direct syntax validation |
| **Quick run command** | `python -m py_compile app.py manage_bot.py config.py services\\google_sheets.py` |
| **Full suite command** | Covered after phase 6 adds dedicated tests |

## Coverage

| Requirement | Behavior | Test |
|-------------|----------|------|
| OPS-01 | Startup validates required config and Sheets schema | Focused validation tests added in phase 6 |
| OPS-02 | Double-start / occupied-port cases fail clearly | Runtime/process-manager path review and syntax check |
| OPS-03 | Duplicate and backup files are ignored from active workflow | `.gitignore` and repo policy update |

## Sign-Off

- [x] Config validation added.
- [x] Schema validation added.
- [x] Port/process failure messages improved.
- [x] Documentation updated.
