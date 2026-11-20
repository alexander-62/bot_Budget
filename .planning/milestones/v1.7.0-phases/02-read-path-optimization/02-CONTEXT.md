# Phase 2 Context: Read Path Optimization

## Objective

Reduce repeated full-sheet reads in the common budget, recent-expense, and shopping-list flows while keeping the current Google Sheets-backed storage model.

## Scope

- Reuse one short-lived monthly budget snapshot across budget and category views.
- Read only a bounded tail range for recent expenses.
- Batch shopping-list inserts so one multi-item message does not issue one write per item.

## Existing Constraints

- Keep the current service and handler boundaries.
- Preserve the existing spreadsheet layout.
- Avoid touching secret-bearing files.

## References

- `.planning/ROADMAP.md`
- `.planning/REQUIREMENTS.md`
- `services/budget.py`
- `services/expenses.py`
- `services/shopping.py`
- `handlers/shopping.py`

