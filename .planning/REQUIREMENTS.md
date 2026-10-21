# Requirements: v1.6.0 Multiple Budget Bots

**Defined:** 2026-10-21
**Core value:** Быстро и надёжно записывать расходы в независимые бюджеты из одной панели.

## v1 Requirements

### Profiles

- [x] **PROF-01**: Произвольное число профилей без изменения кода: ID, имя, таблица, валюта, часовой пояс, автозапуск.
- [x] **PROF-02**: Существующий личный бот работает с прежними настройками и данными без ручной миграции.
- [x] **PROF-03**: Токены отдельно от JSON, Git и журналов; некорректные ID, повторный Telegram-бот или таблица отклоняются.

### Data and access

- [x] **DATA-01**: У каждого бота собственная таблица, категории и Users; разрешённые пользователи видят общий бюджет только своего бота.
- [x] **DATA-02**: RUB в бизнес-расходах, итогах и сводках; EUR у personal. Дата и сводки учитывают часовой пояс профиля.
- [x] **AUTH-03**: Новые профили проверяют числовой Telegram user ID; legacy-доступ личного бота сохраняется.

### Process management

- [x] **PROC-01**: Независимые запуск/остановка/перезапуск, память, PID, блокировки, журналы.
- [x] **PROC-02**: Health сверяется с профилем и PID; чужой процесс на старом порту не показывает ложную готовность.
- [x] **PROC-03**: Одна панель и трей; Windows-автозапуск запускает только отмеченные профили.

### Desktop panel

- [x] **UI-01**: Выбор бота, состояние, управление, открытие его таблицы и журнала.
- [x] **UI-02**: Добавление/редактирование с маскированным токеном; третий бот подключается без изменения исходников.
- [x] **UI-03**: Telegram-токен и схема Sheets проверяются до сохранения; безопасные ошибки и отзывчивый UI.
- [x] **UI-04**: Запоздалый ответ не применяется к другому профилю; работающий профиль нельзя незаметно перенастроить.

### Verification and onboarding

- [x] **TEST-05**: Fakes подтверждают изоляцию двух профилей и добавление третьего; старые tests проходят без секретов/живых записей.
- [x] **DOC-01**: Руководство: Telegram-бот, схема бизнес-таблицы, Users IDs, доступ сервисного аккаунта, RUB-профиль в панели.

## Phase 13 Requirements — Optional money sources

- [x] **SRC-01**: Each bot profile has a persisted boolean source-tracking setting, default false for existing and personal profiles, editable in the desktop form.
- [x] **SRC-02**: Enabled profiles read active sources from their own «Источники» Sheet; disabled profiles do not require/read it. Startup/connection validation enforces the optional schema only when enabled.
- [x] **SRC-03**: Enabled expense entry requires source selection before amount; callbacks remain safe when lists change or sessions expire.
- [x] **SRC-04**: Expense source is stored in I without moving H expense_id; old rows remain blank and source survives amount/comment edits and feature disabling.
- [x] **SRC-05**: Enabled confirmation, recent expenses and saved editing show/allow changing source; source edits preserve amount/comment and stable record identity.
- [x] **SRC-06**: Fake-based flow/data/UI regression tests pass; business setup documents the toggle and optional schema without live financial writes.

All SRC requirements map to phase 13. Prior 15 requirements remain complete.

## Phase 14 Requirements — Panel pictures

- [ ] **IMG-01**: Each profile has a backward-compatible local image setting; old profiles use the existing default logo/initial.
- [ ] **IMG-02**: Operator chooses or clears a picture for any selected bot, including running and legacy personal, without tokens/network or other settings changes.
- [ ] **IMG-03**: Imported assets are bounded valid managed copies; card/icon selection and late worker completion cannot use another profile's picture or overwrite newer metadata.
- [ ] **IMG-04**: Generated-image and real-widget regressions, full suite, visual QA and local-asset documentation pass; Telegram avatars remain outside scope.

All IMG requirements map to phase 14. User explicitly confirmed pictures only in the panel.

## Future Requirements

Серверное размещение, удалённая панель, общий ограничитель Sheets-нагрузки, база данных при измеренной необходимости, явная миграция личного доступа на ID, профильный выбор shopping/limits.

## Out of Scope

SaaS/биллинг, гарантия бесконечной одновременной нагрузки, расширение прав изменения чужих расходов, автоматические живые финансовые записи при тестировании.

## Traceability

| Requirement | Phase | Status |
|---|---|---|
| PROF-01 | 9 | Complete |
| PROF-02 | 9 | Complete |
| PROF-03 | 9 | Complete |
| DATA-01 | 9 | Complete |
| DATA-02 | 9 | Complete |
| AUTH-03 | 9 | Complete |
| PROC-01 | 10 | Complete |
| PROC-02 | 10 | Complete |
| PROC-03 | 10 | Complete |
| UI-01 | 11 | Complete |
| UI-02 | 11 | Complete |
| UI-03 | 11 | Complete |
| UI-04 | 11 | Complete |
| TEST-05 | 12 | Complete |
| DOC-01 | 12 | Complete |
| SRC-01 | 13 | Complete |
| SRC-02 | 13 | Complete |
| SRC-03 | 13 | Complete |
| SRC-04 | 13 | Complete |
| SRC-05 | 13 | Complete |
| SRC-06 | 13 | Complete |

Coverage: 21 requirements, all mapped once. Previous: milestones/pre-v1.6.0-REQUIREMENTS.md.

Verified 2026-10-21: implementation complete; 109 tests/25 modules pass; phase 13 optional sources verified. Live business onboarding remains operator action.
