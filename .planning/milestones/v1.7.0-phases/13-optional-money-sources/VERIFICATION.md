---
phase: 13-optional-money-sources
status: passed
verified: 2026-10-21
score: 6/6
---

# Goal-backward verification

| Requirement | Evidence | Result |
|---|---|---|
| SRC-01 | BotProfile strict flag/default; copied-config subprocess tests for absent flag, false and true; real desktop form tests true/false | Passed |
| SRC-02 | Central adapter, filtering/sorting/deduplication of own-sheet values; optional connection/startup schema and nonempty-list checks | Passed |
| SRC-03 | Snapshot + UUID callback generation; active recheck, malformed/foreign/stale/expired and refreshed-index regressions | Passed |
| SRC-04 | A:I enabled versus A:H disabled; identity H retained; amount edits and disabled writes preserve I and historical blanks; stale source guard | Passed |
| SRC-05 | Escaped confirmation/recent source; optional source edit preserves amount/comment; amount edit retains inactive/blank source; cancel keeps expense | Passed |
| SRC-06 | 109 tests/25 modules, zero publication findings, clean diff check; README/Google setup and fake-profile form visual QA | Passed |

Commands: `.venv/Scripts/python.exe scripts/run_tests.py`, `.venv/Scripts/python.exe scripts/check_publication.py`, `git diff --check`. Full UTF-8 test log: ignored local `artifacts/source-tests-final.txt`.

Independent focused review found no remaining blockers after picker-generation correction. GLOBAL_USER event isolation serializes concurrent updates in production; existing dispatcher regression tests exercise the boundary.

## Operator rollout pending

The real bot runs on another computer. No push or runtime deployment was performed. For business: add Sheet «Источники» (A источник, B активно, C порядок), add I1 «источник» to expense Sheet, stop profile, enable checkbox, validate/save and start. Personal stays disabled by default; its Sheet needs no change. Live Telegram/Sheets entry remains an operator check and is not claimed as performed.
