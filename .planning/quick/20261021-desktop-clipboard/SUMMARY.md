# Desktop clipboard hotfix — v1.6.3

Implemented explicit Windows virtual-key Ctrl+V/C/X/A handling for profile-form entries, Shift+Insert and right-click/keyboard context menu. CTk forwards the binding to the native Entry before Tk class bindings; handled shortcuts stop propagation to avoid double paste. Other keys and Alt/AltGr remain native.

Paste reads before deleting selection, so an empty/non-text/unavailable clipboard leaves field content intact. Disabled/readonly fields remain immutable; masked token keeps its show setting. Clipboard content is never logged. Native copy/cut/select behavior is retained.

Six regression tests passed using real CTk/Tk fields and generated fake clipboard data. Even fallback Tk class clipboard reads are intercepted in the test Tcl interpreter, and copy/cut virtual actions are mocked; tests neither read nor overwrite the user's real clipboard. Covered native key binding/single insertion, Russian keysym+Windows keycode, masked token, Shift+Insert, selected replacement, missing/empty clipboard, readonly, Alt, and context menu states.

Sheets validation now provides app-authored diagnostics for file path/permissions, malformed keys, authorization, table sharing, disabled APIs, quotas and connectivity. Raw transport messages are never shown. Two additional tests cover error variants with secret-like markers and the unchanged empty-field shared-key fallback. README explains common-key resolution and separate table sharing.

Full installed-dependency runner: 130 tests in 28 isolated modules, zero failures. Publication scanner: zero findings. Diff check: clean. Evidence: local ignored artifacts/clipboard-tests-final.txt.

No bot process, real user token, Sheet or local secret was changed. User AGENTS.md edits stay outside this fix. Delivery target is origin/main for the user's already authorized remote-computer update workflow. Operator should exit the old panel, run bot.bat update, reopen bot.bat ui and retry paste.
