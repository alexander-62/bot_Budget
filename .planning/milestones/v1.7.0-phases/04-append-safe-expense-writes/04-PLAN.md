# Phase 4 Plan: Append-Safe Expense Writes

## Objective

Make expense writes append-safe and expose saved-row identity without breaking the current expense flow.

## Implementation Tasks

1. Remove the full-sheet next-row scan from `services/expenses.py`.
2. Write expenses with Google Sheets append semantics.
3. Return a structured saved-expense result that includes the saved row identity.
4. Keep `parse_amount()` and `parse_amount_with_optional_comment()` behavior unchanged.
5. Update the expense handler to consume the new result without changing user-visible behavior yet.
6. Run a syntax check on the touched modules.

## Verification

1. Run `python -m py_compile` on the touched modules.
2. Confirm the expense handler still finalizes and posts the category card after save.
