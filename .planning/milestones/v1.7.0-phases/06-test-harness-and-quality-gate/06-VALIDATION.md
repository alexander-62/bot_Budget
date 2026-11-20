---
phase: 6
slug: test-harness-and-quality-gate
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-29
---

# Phase 6 Validation Strategy

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `unittest` |
| **Quick run command** | `python -m unittest` on focused phase 6 test modules |
| **Full suite command** | `python -m unittest discover -s tests -p 'test_*.py'` |

## Coverage

| Requirement | Behavior | Test |
|-------------|----------|------|
| TEST-01 | Amount parsing and optional comments behave correctly | Parsing unit tests |
| TEST-02 | Access checks tolerate malformed `Users` rows | Access unit tests with fakes |
| TEST-03 | Adapter caching and write behavior avoid live secrets | Sheets/expense fake-based tests |
| TEST-04 | App imports, keyboards, dispatcher build cleanly | Smoke checks |

## Sign-Off

- [x] Parsing tests added.
- [x] Access tests added.
- [x] Sheets/write tests added.
- [x] Smoke checks added.
