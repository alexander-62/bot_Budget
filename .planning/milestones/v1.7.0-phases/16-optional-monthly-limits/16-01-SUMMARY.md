---
phase: 16
plan: 01
status: complete
completed: 2026-10-22
---

# Учёт расходов без месячных лимитов

Выключенный режим не читает и не требует лист лимитов, сохраняет суммы и показывает расходы без потолка/остатков. Пустой лимит отличается от нуля. Отчёты включают расходы архивных категорий; новые траты предлагают только активные пары.

Requirements: LIM-01, LIM-02.

Validation: 180 tests across 33 isolated modules; all modules pass with virtual display, one Windows DPAPI test skipped on Linux. New settings/category/desktop coverage includes 29 tests. Runtime smoke, compile/AST and diff checks pass. Publication audit: zero findings. No live Sheet, credentials, financial records or production bot changed.
