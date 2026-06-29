# Phase 7 Context: Autosave Expense UX

## Objective

Remove extra save-confirmation step and replace it with fast post-save actions built on saved expense identity.

## Scope

- Save expense immediately after amount/comment entry.
- Show concise saved-expense summary with edit action.
- Add next-action buttons for same-category repeat and fresh expense entry.
- Keep edit/delete callbacks safe by checking saved-record identity before mutating a row.

## Existing Constraints

- Must build on saved expense identity from phase 4.
- Keep handler routing in `handlers/` and keyboard building in `keyboards/`.
- Reject stale or replayed callbacks safely.

## References

- `.planning/ROADMAP.md`
- `.planning/REQUIREMENTS.md`
- `handlers/expenses.py`
- `keyboards/expenses.py`
- `services/expenses.py`
- `state/expense_session.py`

