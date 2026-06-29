# Phase 4 Context: Append-Safe Expense Writes

## Objective

Make expense creation race-resistant and return enough saved-record identity for later edit/delete work.

## Scope

- Replace the full-sheet next-row scan in `services/expenses.py` with Google Sheets append semantics.
- Return a structured saved-expense result that includes row identity and saved values.
- Keep the existing add-expense confirmation flow working during the service transition.
- Preserve amount parsing and optional inline comments.

## Existing Constraints

- Keep Google Sheets as the durable store for this milestone.
- Preserve the current handler/service boundary.
- Do not change secret-bearing files.
- Avoid schema changes unless they are required for safe append identity.

## References

- `.planning/ROADMAP.md`
- `.planning/REQUIREMENTS.md`
- `handlers/expenses.py`
- `services/expenses.py`
- `services/google_sheets.py`
