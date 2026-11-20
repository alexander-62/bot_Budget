# Phase 5 Context: Operational Reliability Cleanup

## Objective

Make startup failures, process state, and repository noise easier to understand before final UX work.

## Scope

- Validate required runtime config names and required Google Sheets worksheets/headers with actionable errors.
- Make occupied Web App port and double-start situations fail clearly.
- Reduce confusion from duplicate and backup files by ignoring non-authoritative copies.
- Update operational documentation to match actual start/stop/update flow.

## Existing Constraints

- Do not read or print secret values.
- Keep Google Sheets access centralized in `services/google_sheets.py`.
- Do not delete user data or secret files.

## References

- `.planning/ROADMAP.md`
- `.planning/REQUIREMENTS.md`
- `app.py`
- `config.py`
- `constants.py`
- `manage_bot.py`
- `.gitignore`
- `README.md`

