---
phase: 3
slug: async-responsiveness-boundary
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-29
---

# Phase 3 Validation Strategy

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `unittest` / direct syntax validation |
| **Quick run command** | `python -m py_compile app.py handlers\\expenses.py handlers\\menu.py handlers\\shopping.py services\\access.py services\\async_tools.py` |
| **Full suite command** | Not added in this phase; covered later by dedicated tests |

## Coverage

| Requirement | Behavior | Test |
|-------------|----------|------|
| ASYNC-01 | Blocking Sheets calls go through an async boundary | `python -m py_compile ...` and handler/service call-site review |
| ASYNC-02 | Handlers keep responses and callback acknowledgements responsive | Handler-level call-site audit in `handlers/expenses.py`, `handlers/menu.py`, `handlers/shopping.py` |
| ASYNC-03 | Startup notification chat-id loading no longer blocks polling startup | `app.py` wraps `get_allowed_chat_ids()` through the async helper |

## Sign-Off

- [x] Async boundary added at handler and startup entry points.
- [x] Syntax check passed in the current workspace.

