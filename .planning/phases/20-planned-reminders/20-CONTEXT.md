# Phase 20: Напоминания — Context

## Locked decisions

User approved autonomous implementation of the proposed MVP, branch feat/planned-expenses. Google Sheets remains durable store. Flag is per-profile, default false; first version has one-off/full payments. Existing architecture boundaries and access rules apply. Name/category/subcategory required, planned amount/date optional. Creator receives reminders independently from daily digest. Other allowed participants can manage/pay shared plans. Payment actor is persisted separately from creator.

## Implementation decisions

Use a stable UUID for plans, optimistic revision tokens for edits/payment confirmation, per-process RLock and atomic Sheets batchUpdate for payment. Never retry an ambiguous append without re-reading state. Reminder delivery is at-least-once if Telegram succeeds but persisting delivery fails; no impossible exactly-once Telegram promise. Persist date buckets per planned item, not process memory. No additional external dependencies.

## Scope and verification

Создатель получает своевременные независимые напоминания.
Tests: tests/test_planned_reminders.py tests/test_planned_flow.py. All external calls use fakes; live acceptance pending. User authorization replaces routine interactive confirmations. Execute sequentially inline because no subagents were explicitly requested; verify plans and implementation separately.
