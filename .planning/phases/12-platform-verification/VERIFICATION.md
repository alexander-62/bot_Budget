---
phase: 12-platform-verification
status: passed
verified: 2026-10-21
---

TEST-05: `.venv/Scripts/python.exe scripts/run_tests.py` => 21 modules, 89 test cases, 0 failed. Includes full installed-dependency smoke and generated two-worker isolation test.

DOC-01: README links to business setup; guide specifies five sheets, exact header positions, numeric participant IDs, access grant, RUB profile creation and operator-owned first expense.

Other checks: publication audit 0 findings; git diff --check clean; git check-ignore confirms profiles.json, .profile-secrets, .runtime, root process-identity and allocation/registry locks ignored. Evidence log: local ignored artifacts/multibot-tests-final.txt.

## Release and rollout boundary

Implementation is complete and ready for operator onboarding. Real business bot is not configured because its token/table were not supplied. Next action: `bot.bat ui` → «Добавить бота» → separate business token/table + RUB → «Проверить и сохранить». Then operator tests /start and first expense in that bot, confirming personal table remains untouched. No claim of live end-to-end rollout is made.
