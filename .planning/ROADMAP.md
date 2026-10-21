# Roadmap: v1.6.0 Multiple Budget Bots

**Created:** 2026-10-21. Пользователь поручил исполнить согласованную архитектуру.
Предыдущие фазы 1–8 сохранены; старая карта: milestones/pre-v1.6.0-ROADMAP.md.

| Phase | Goal | Requirements | Status |
|---|---|---|---|
| 9. Bot Profiles | Профили, секреты, валюты, доступ, совместимость | PROF-01, PROF-02, PROF-03, DATA-01, DATA-02, AUTH-03 | Complete |
| 10. Profile Processes | Независимый запуск, health и автозапуск | PROC-01, PROC-02, PROC-03 | Complete |
| 11. Multi-Bot Panel | Добавление, проверка и управление в панели | UI-01, UI-02, UI-03, UI-04 | Complete |
| 12. Platform Verification | Изоляция, регрессии, документация | TEST-05, DOC-01 | Complete |

## Phase 9: Bot Profiles

**Goal:** Общий код работает с изолированными настройками, личный бот совместим.
**Depends on:** Previous implementation.
**Success criteria:**
1. Personal использует прежнюю конфигурацию/таблицу и EUR.
2. Новый профиль не наследует личный токен/таблицу; секреты не входят в реестр/repr/logs.
3. Категории и доступ по ID относятся к собственной таблице.
4. Валюта и часовой пояс применяются к расходам/сводкам.
**Plan:** phases/09-bot-profiles/09-01-PLAN.md.

## Phase 10: Profile Processes

**Goal:** Управление одним ботом не затрагивает остальные.
**Depends on:** Phase 9.
**Success criteria:**
1. Раздельные процессы, PID/lock/log и память.
2. Повторные старты и health другого профиля отклоняются.
3. Панель/трей общие, автозапуск учитывает только выбранные профили.
**Plan:** phases/10-profile-processes/10-01-PLAN.md.

## Phase 11: Multi-Bot Panel

**Goal:** Добавить третий бот и управлять им без изменения кода.
**Depends on:** Phase 9, Phase 10.
**Success criteria:**
1. Статус/команды/таблица/журнал относятся к выбранному боту.
2. Добавление и редактирование проверяют Telegram и Sheets, не показывают токены.
3. UI остаётся отзывчивым; запоздалый результат не подменяет выбранный профиль.
4. Работающий профиль не перенастраивается незаметно.
**Plan:** phases/11-multi-bot-panel/11-01-PLAN.md.

## Phase 12: Platform Verification

**Goal:** Подтвердить изоляцию и документировать подключение бизнеса.
**Depends on:** Phase 9, Phase 10, Phase 11.
**Success criteria:**
1. Все тестовые модули и межпрофильные проверки проходят без живых записей.
2. Регрессии проверены; реестр/секреты/runtime исключены из Git.
3. Документация содержит схему таблицы и путь подключения RUB-профиля. Живое подключение не выдается за выполненное без токена и таблицы.
**Plan:** phases/12-platform-verification/12-01-PLAN.md.

## Execution notes

Секции реализации делегированы экономичной модели по непересекающимся файлам и общей API-спецификации. Интеграция следует зависимостям фаз. Пользовательские изменения AGENTS.md не входят в коммиты.
## Next step

Implementation phases 9?12 complete, version 1.6.0. Open `bot.bat ui` and add the actual business bot and separate Sheet with RUB. Live token/table onboarding and first real expense remain unperformed.
