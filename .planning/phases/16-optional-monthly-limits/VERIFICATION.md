# Phase 16 verification

Status: passed (automated). Date: 2026-10-22.

Выключенный режим не читает и не требует лист лимитов, сохраняет суммы и показывает расходы без потолка/остатков. Пустой лимит отличается от нуля. Отчёты включают расходы архивных категорий; новые траты предлагают только активные пары.

Evidence: tests/test_budget_settings.py, tests/test_category_settings.py, tests/test_budget_settings_desktop.py plus unchanged isolated regression suite. Full virtual-display run: 180 tests / 33 modules / 0 failed modules; 1 Windows-only DPAPI skip. Old clipboard test now generates a native V keysym on X11 instead of a Windows-only virtual keycode; production clipboard code unchanged.

Environment: Python 3.12, dependencies installed from requirements.txt. Xvfb unpacked in /tmp; PYSTRAY_BACKEND=dummy to avoid accessing the host tray. Tests use fakes and generated values. Sandbox prevented asyncio executor wakeups, so final tests ran with local sockets available. GSD documents maintained in the existing repository format; no GSD CLI was available.

Operator acceptance still required after delivery: update/reopen panel, start each bot, verify migrated currency, limits off/on, create a category/subcategory and record a real expense deliberately. No live rollout is claimed.
