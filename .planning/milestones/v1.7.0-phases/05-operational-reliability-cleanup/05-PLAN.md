# Phase 5 Plan: Operational Reliability Cleanup

## Objective

Catch bad runtime setup early and make local operations less ambiguous.

## Implementation Tasks

1. Add explicit startup validation for required config names.
2. Add Google Sheets worksheet/header validation with actionable error messages.
3. Improve Web App port-start failure handling in runtime and process-manager paths.
4. Add ignore rules for backup and duplicate local files that are not authoritative runtime sources.
5. Update `README.md` to describe the actual process workflow and startup failure modes.
6. Run focused syntax checks on touched modules.

## Verification

1. Run `python -m py_compile` on touched runtime modules.
2. Review startup validation errors for missing config/schema names without exposing secret values.

