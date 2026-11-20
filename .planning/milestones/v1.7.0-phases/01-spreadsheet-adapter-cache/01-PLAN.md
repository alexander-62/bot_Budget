# Phase 1 Plan: Spreadsheet Adapter Cache

## Objective

Centralize and cache Google Sheets client, spreadsheet, and worksheet lookup behavior so the bot stops paying the setup cost on every service call.

## Scope

This phase only changes the Google Sheets adapter and the code that directly depends on it for client/spreadsheet/worksheet access. It does not change business logic, sheet schema, or user-facing flows.

## Requirements Addressed

- PERF-01: Bot reuses a cached gspread client and spreadsheet object.
- PERF-02: Bot reuses worksheet lookups by normalized worksheet name.

## Implementation Tasks

1. Add adapter-level cache state in `services/google_sheets.py` for the authorized gspread client, the opened spreadsheet, and normalized worksheet lookups.
2. Expose a cache reset helper for tests and for any future recovery path that needs a clean adapter state.
3. Keep `get_spreadsheet()` as the single public entry point for callers, but make it reuse the cached spreadsheet object instead of reopening Google Sheets each time.
4. Keep `find_worksheet_case_insensitive()` as the single public worksheet resolver, but make it return cached worksheet objects on repeat calls.
5. Preserve existing exceptions and return types so access, budget, expense, and shopping services do not need behavior changes in this phase.

## Files To Change

- `services/google_sheets.py`
- `tests/` or a small smoke test file if needed to exercise cache reset behavior

## Verification

1. Run a Python compile check for the touched module.
2. Run a focused smoke test or import check that exercises `get_spreadsheet()` twice and confirms the same object is reused in-process.
3. Confirm repeated worksheet lookup for the same sheet title returns the cached object.
4. Confirm no secrets file is read or printed during verification.

## Risks

- Cached worksheet objects may become stale if the sheet structure changes during the process lifetime.
- A process restart or explicit cache reset must clear stale adapter state cleanly.
- If tests rely on fresh object identity, they must call the cache reset helper first.

## Done

- `services/google_sheets.py` uses cached client/spreadsheet/worksheet state.
- Behavior remains compatible with existing service callers.
- Basic verification passes.
