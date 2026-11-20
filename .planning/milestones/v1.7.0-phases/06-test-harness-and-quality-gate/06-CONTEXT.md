# Phase 6 Context: Test Harness and Quality Gate

## Objective

Add enough automated coverage to change parsing, access checks, Sheets adapters, and app wiring safely.

## Scope

- Add focused unit tests for amount parsing and optional comments.
- Add focused unit tests for access normalization and malformed `Users` rows.
- Add tests for adapter caching and new expense-write behavior without real Google credentials.
- Add a smoke check that imports app modules, builds keyboards, and creates dispatcher under installed dependencies.

## Existing Constraints

- Prefer mocks and fakes over live Google Sheets calls.
- Normal unit tests must not require `secrets.py` or real credentials.
- Smoke coverage may need test-time stubs when optional runtime deps are absent in current workspace.

## References

- `.planning/ROADMAP.md`
- `.planning/REQUIREMENTS.md`
- `tests/`
- `services/access.py`
- `services/expenses.py`
- `services/google_sheets.py`
- `app.py`

