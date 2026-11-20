# Phase 3 Context: Async Responsiveness Boundary

## Objective

Move blocking Google Sheets-backed work off the aiogram event loop so slow Sheets calls do not stall unrelated Telegram updates.

## Scope

- Wrap Sheets-backed service calls at the handler boundary with `asyncio.to_thread` or an equivalent helper.
- Keep callback acknowledgements responsive while expensive reads or writes run in worker threads.
- Move startup notification chat-id loading off the main polling path.

## Existing Constraints

- Keep the current sync service layer unless a later phase explicitly changes it.
- Preserve handler/service boundaries.
- Avoid touching secret-bearing files.

## References

- `.planning/ROADMAP.md`
- `.planning/REQUIREMENTS.md`
- `app.py`
- `handlers/expenses.py`
- `handlers/menu.py`
- `handlers/shopping.py`
- `services/access.py`

