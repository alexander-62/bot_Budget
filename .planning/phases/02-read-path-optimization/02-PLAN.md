# Phase 2 Plan: Read Path Optimization

## Objective

Make the frequent read paths pay for Google Sheets data loading once per user action instead of once per helper call.

## Implementation Tasks

1. Add a short-lived monthly budget snapshot cache in `services/budget.py`.
2. Reuse the cached snapshot from `get_budget_limits()`, `get_month_totals()`, and `get_category_details()`.
3. Add an explicit cache reset helper so later write phases can invalidate the snapshot after mutations.
4. Change `services/expenses.py` to read a bounded tail range for recent-expense queries.
5. Add a batch shopping insert helper that loads existing entries once and appends all new rows together.
6. Update the shopping handler to use the batch helper for comma-separated item input.
7. Add focused tests for snapshot reuse, bounded recent-expense reads, and batch shopping writes.

## Verification

1. Run `python -m py_compile` on the touched modules.
2. Run the focused unit tests for the phase 2 read paths.

