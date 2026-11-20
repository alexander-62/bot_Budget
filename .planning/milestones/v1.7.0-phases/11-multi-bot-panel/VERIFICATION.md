---
phase: 11-multi-bot-panel
status: passed
verified: 2026-10-21
---

UI-01/02/03/04 supported by passing tests and visual inspection of panel and form. Test coverage includes explicit command profile, stale status/action callbacks, switching before/during save, same-profile refresh, cancellation, worker startup during validation, duplicate identity, invalid fields, safe transport failures and cached adapter preservation.

Operator check pending: add actual BotFather token and prepared business Sheet, then confirm real Telegram/Sheets connection. Saved tokens cannot be recovered on another Windows account; operator must re-enter them there. Legacy personal settings intentionally remain in existing configuration.
