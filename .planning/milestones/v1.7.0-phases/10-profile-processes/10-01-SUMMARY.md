---
phase: 10-profile-processes
plan: 01
status: complete
requirements_completed: [PROC-01, PROC-02, PROC-03]
completed: 2026-10-21
---

# Phase 10 — implemented

Manager accepts explicit --profile and --all; worker environment selects the profile. PID, port, identity, logs and locks are per profile. A global port-allocation lock prevents simultaneous starts choosing the same port. Birth identity (GetProcessTimes / Linux proc starttime) prevents stale PID ownership mistakes. Stop can handle an unresponsive own startup and refuses unrelated PIDs. Refused operations exit nonzero; failed kills preserve diagnosis metadata.

Desktop/tray remain global and discard inherited worker profile settings. Health identity and PID are checked before state is attributed. Windows autostart opens the shared panel and starts only marked profiles. Legacy v1.5 personal health lacking profile_id is accepted only for legacy personal with matching PID; nonlegacy profiles cannot claim it.

Verification: 17 profile-process tests plus desktop-services, process-control and runtime single-instance tests pass; final full suite 89/89. Two-thread fake allocation, reused PID, unknown ownership, legacy migration, independent workers and enabled-only autostart covered. No real bot processes were started or stopped.
