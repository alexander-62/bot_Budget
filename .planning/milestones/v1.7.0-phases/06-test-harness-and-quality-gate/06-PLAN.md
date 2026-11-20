# Phase 6 Plan: Test Harness and Quality Gate

## Objective

Add repeatable automated checks around the highest-risk service and wiring paths.

## Implementation Tasks

1. Add parsing tests for `parse_amount()` and `parse_amount_with_optional_comment()`.
2. Add access tests for username normalization, malformed rows, and cache-backed sync behavior.
3. Add expense-write tests for append semantics and saved-row identity.
4. Add startup/config validation tests with fakes.
5. Add smoke checks for module import, dispatcher creation, and keyboard builders.
6. Document the test commands in phase summary and project docs.

## Verification

1. Run focused `unittest` modules for parsing, access, expense writes, and validation.
2. Run smoke checks in environment available in current workspace.

