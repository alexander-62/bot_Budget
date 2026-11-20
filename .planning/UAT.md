---
status: testing
milestone: v1.8.0
started: "2026-11-20T20:05:48.245898+00:00"
updated: "2026-11-20T20:05:48.245898+00:00"
---

# Operator Acceptance: v1.8.0

The autonomous implementation and automated checks are complete. These real-computer checks are pending deployment; no live result is inferred from fakes. Use a test budget for financial acceptance.

## Current Test

number: 1
name: Enable feature in updated Windows panel
awaiting: operator deployment and acceptance

## Tests

### 1. Profile switch and compatibility
expected: Existing profile remains unchanged with feature off. Enable future expenses for one test profile, let the panel restart that bot, send /start; only that bot gains the menu and initializes Будущие_траты.
result: [pending]

### 2. Plan and payment
expected: In the test budget create a plan without date/amount, edit it, confirm an actual amount and yesterday's date/source. One actual row appears, plan moves to history with actor and expense_id. Old buttons cannot duplicate it. Other budget stays unchanged.
result: [pending]

### 3. Personal reminders
expected: At 21:30 profile time creator receives dated reminders and Monday undated digest. Disabling future reminders affects no ordinary daily digest. Restart does not resend an acknowledged bucket. Reminder opens the current plan.
result: [pending]

### 4. Disable and retain data
expected: Turning off the profile flag hides the menu and stops reminders/old callbacks. Re-enabling restores saved plans and history.
result: [pending]

### 5. Snooze, recurrence and forecast
expected: Set a custom reminder date and confirm the payment due date stays the same. Set a weekly or monthly schedule and review the forecast over the next seven days and the rest of the month.
result: [pending]

### 6. Correct an expense or reopen a plan
expected: As the payer, edit the date and amount, then undo the posting. Check totals, open status and history before paying again.
result: [pending]

### 7. Recover a payment in the panel
expected: Open the selected budget's recovery window. Inspect an unfinished attempt and stop the corresponding bot before confirming recovery. Check that exactly one actual expense exists.
result: [pending]

## Summary

total: 7
passed: 0
issues: 0
pending: 7
skipped: 0

## Automated Evidence

243 tests in 43 isolated modules, with 242 passed and one Windows DPAPI skip. Phase-specific reports under phases/18-*, phases/19-*, phases/20-* record exact source fingerprints. Automated failure injections cover ambiguous and delayed financial responses without any live financial writes.
