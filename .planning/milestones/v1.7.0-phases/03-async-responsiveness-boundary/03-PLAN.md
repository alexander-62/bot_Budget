# Phase 3 Plan: Async Responsiveness Boundary

## Objective

Make blocking Google Sheets calls safe for the asyncio bot by moving them behind a small async wrapper.

## Implementation Tasks

1. Add a tiny helper for running blocking callables in a worker thread.
2. Wrap access checks so `is_allowed_username()` and chat-id sync do not block the event loop.
3. Wrap budget, expense, and shopping service calls in handlers with the async helper.
4. Move startup notification chat-id loading off the main polling path.
5. Keep user-facing responses and callback acknowledgements immediate where possible.
6. Run a syntax check on the touched modules.

## Verification

1. Run `python -m py_compile` on the touched modules.
2. Confirm the updated handlers still import and dispatch cleanly.

