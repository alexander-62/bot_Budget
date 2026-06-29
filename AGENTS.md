# Agent Guidance

This is an existing Python Telegram budget bot backed by Google Sheets.

## Project Context

- Read `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md`, and `.planning/ROADMAP.md` before planning or implementing milestone work.
- Read `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/STACK.md`, and `.planning/codebase/CONCERNS.md` before changing service or handler structure.
- Do not read, print, or commit `secrets.py` or `credentials.json`.

## Codebase Rules

- Active runtime files are the normal module names, not backup copies such as `handlers/expenses (2).py`, `services/expenses (2).py`, or `*.bak_test`.
- Keep Telegram routing in `handlers/`, keyboard construction in `keyboards/`, in-memory flow state in `state/`, and domain/Sheets logic in `services/`.
- Keep Google Sheets access centralized through `services/google_sheets.py`.
- The bot works with Cyrillic Russian user-facing text. Always treat source files, logs, exports, generated docs, and command output as UTF-8 unless there is direct evidence otherwise.
- Be especially careful in PowerShell: console output may display UTF-8 text as mojibake when the terminal code page or output encoding is wrong. Do not rewrite, "fix", or transliterate Russian text based only on garbled PowerShell display.
- When reading or writing files from scripts or shell commands, specify UTF-8 explicitly where the tool supports it, for example `-Encoding UTF8` in PowerShell or `encoding="utf-8"` in Python. Avoid commands that silently use a legacy Windows code page for Cyrillic content.

## Current Roadmap

1. Cache Google Sheets adapter objects.
2. Optimize read paths.
3. Add an async boundary for blocking Sheets calls.
4. Make expense writes append-safe and return saved-record identity.
5. Improve operational reliability.
6. Add tests and smoke checks.
7. Improve expense-entry UX with autosave and next-action buttons.

## Verification

- Prefer tests and fakes over live Google Sheets calls.
- Do not require local secrets for normal unit tests.
- For runtime checks, install dependencies from `requirements.txt` in the active environment first.
