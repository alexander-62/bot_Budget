# Phase 7 Plan: Autosave Expense UX

## Objective

Cut one click from expense entry and keep users in flow after a save.

## Implementation Tasks

1. Remove separate save-confirm step from expense entry flow.
2. Save immediately after amount/comment parse succeeds.
3. Add post-save keyboard with edit, same-category repeat, and fresh-expense actions.
4. Add saved-expense action state to reject stale callbacks safely.
5. Add row-identity verification before expense edit/delete mutations.
6. Reuse same category/subcategory context for fast repeated entry.
7. Add focused tests for saved-expense actions and stale-callback rejection.

## Verification

1. Run syntax checks on touched expense handler/service/state/keyboard modules.
2. Run focused tests covering autosave and saved-expense actions.

