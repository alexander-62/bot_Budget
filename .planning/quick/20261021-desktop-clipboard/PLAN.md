# Desktop clipboard hotfix — v1.6.3

User reports text cannot be pasted into the add-bot form on another Windows computer. Treat this as a product bug; keep existing phase history and resolve as a small desktop fix.

1. Add explicit Entry shortcut handling for Ctrl+V/C/X/A using Windows virtual key codes, independent of the current English/Russian keysym; support Shift+Insert and a labeled context menu on each text field, including masked token.
2. Preserve native copy/cut/select behavior, ignore Alt/AltGr combinations, keep disabled/readonly IDs immutable and keep selected text on an empty/non-text clipboard. Never log clipboard contents.
3. Test real Tk fields with generated fake clipboard input, never read/overwrite the user's real clipboard. Check native binding avoids double paste, Cyrillic/token insertion, context menu, readonly and empty clipboard. Run full isolated suite, document version and publish the fix for the existing remote-install workflow authorized by the user.

4. The user's remote-computer screenshot also shows an opaque Sheets validation failure. Replace it with safe, actionable diagnostics for missing/invalid keys, table access, disabled API, quotas and connection errors. Preserve shared-key fallback; test it without reading actual credentials or making live requests.

Scope: desktop form and its validation messages. No bot runtime, actual Sheets, credentials or user's clipboard interaction. Preserve uncommitted user AGENTS.md edits.
