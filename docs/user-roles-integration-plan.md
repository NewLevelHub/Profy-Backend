# Три роли: ученик / админ / психолог — план интеграции

## Status: Milestone 1 implemented (branch `pro-281`), Milestones 2–3 planned, not started

Milestone 1 (роль-инфраструктура) реализован и проверен: `UserRole` enum +
`role` колонка на `User`, `is_admin` стал computed-property, миграция
`12cdf8d6ab06`, `require_role()` в `app/dependencies.py`, `role` в схемах
(`UserInfo`/`UserResponse`/`AdminUserListItem`/`AdminUserDetailResponse`),
новый `POST /api/v1/admin/users` для провижининга admin/psychologist
аккаунтов, тесты (`tests/unit/test_role_permissions.py`,
`tests/integration/test_admin_user_provisioning.py`). Проверено полным
прогоном `pytest` на чистой (throwaway) БД — 375 passed, 8 pre-existing
failures не связанных с ролями (report narrative content, image
content-type mismatch, `UniversityRequirement` schema drift — воспроизведены
и на коде до этого изменения через `git stash`).

Milestones 2 (доступ психолога к назначенным ученикам) и 3 (заметки
психолога) — ещё не начаты, описаны ниже как план.

## Context

До этого изменения в проекте была только одна фактическая роль (ученик,
неявно — через self-registration) и один булевый флаг `is_admin` на `User`.
Полноценной ролевой системы не было: не было enum, не было переиспользуемой
зависимости для проверки прав (кроме `get_current_admin_user`), не было
концепции психолога ни в коде, ни в продукте.

Продуктовые решения (зафиксированы, не пересматривать без явного запроса):

1. **Хранение роли**: `role` — источник истины. `is_admin` — read-only
   computed property поверх `role == UserRole.admin`, депрекейтится
   постепенно (физическая колонка `is_admin` в БД остаётся, просто больше не
   маппится моделью — дроп отдельной cleanup-миграцией позже).
2. **Провижининг**: self-registration (`/auth/register`, Google OAuth)
   остаётся ученик-only. Admin и psychologist аккаунты создаются **только**
   через админку (`POST /api/v1/admin/users`) — без invite-кода и без
   self-registration с выбором роли.
3. **Скоуп психолога**: просмотр результатов/отчётов назначенных учеников,
   привязка психолог↔ученик (через таблицу назначений, не "видит всех"),
   свои заметки/рекомендации по ученику. При отвязке ученика от психолога —
   **soft cutoff**: новые заметки создавать нельзя, старые заметки психолог
   продолжает видеть.

## Сквозные решения

1. `get_current_admin_user` (`app/dependencies.py`) не трогаем — 24
   существующих admin-роута продолжают работать как есть. Рядом добавлена
   независимая фабрика `require_role(*roles: UserRole)`.
2. Психолог никогда не проходит через существующие admin-роуты — получит
   отдельный роутер `app/routers/psychologist.py` на `/api/v1/psychologist`,
   gated `require_role(UserRole.psychologist)`.
3. `admin_service.get_user_detail()` / `get_assessment_detail()`
   (`app/services/admin_service.py:238,325`) принимают голый `user_id` без
   встроенной авторизации — переиспользуются психологом, но только после
   проверки назначения, и через отдельную узкую схему ответа (не отдавать
   `AdminUserDetailResponse` психологу напрямую).
4. `is_admin` остаётся так названным (без переименования) — читается из
   `role` прозрачно через `from_attributes=True`.

## Milestone 1 — Инфраструктура ролей (done)

- `app/models/user.py`: `UserRole(str, enum.Enum)` = `student`/`admin`/
  `psychologist`, по образцу `AgeGroup` в `app/models/profile.py`. Колонка
  `role` (`Enum(UserRole, name="user_role_enum")`, default `student`).
  `is_admin` — `@property`, читает `role == UserRole.admin`.
- Миграция `alembic/versions/12cdf8d6ab06_add_role_to_users.py`: создаёт
  `user_role_enum`, добавляет `role` с backfill из `is_admin`
  (`UPDATE users SET role='admin' WHERE is_admin=true`), затем даёт
  физической колонке `is_admin` `server_default=false` — без этого любой
  новый INSERT ломает NOT NULL, т.к. модель больше её не отправляет.
  Колонку `is_admin` не дропает.
- `app/dependencies.py`: `require_role(*roles)` рядом с нетронутым
  `get_current_admin_user`.
- Схемы: `role` добавлен в `UserInfo`/`UserResponse` (`app/schemas/auth.py`)
  и `AdminUserListItem`/`AdminUserDetailResponse` (`app/schemas/admin.py`).
  Новая `AdminUserCreate` — валидатор отклоняет `role=student` (422).
- `POST /api/v1/admin/users` (`app/routers/admin.py` +
  `admin_service.create_user`) — первый write-эндпоинт у admin для `User`
  (раньше был только read+export). Проверка уникальности email (400 на
  дубликат, тем же паттерном что и `auth_service.register`), без
  email-verification flow (`is_verified` выставляется сразу из тела
  запроса).
- Тесты: `admin_user`/`admin_headers`, `psychologist_user`/
  `psychologist_headers` фикстуры в `tests/conftest.py` (сигнатуры
  `test_user`/`auth_headers` не тронуты). `tests/unit/test_role_permissions.py`
  — матрица 403 для `get_current_admin_user`/`require_role`. `tests/
  integration/test_admin_user_provisioning.py` — round-trip для нового
  эндпоинта.
- `app/services/admin_export_service.py`: `role` добавлен в CSV-экспорт
  списка юзеров (`_USER_COLUMNS`) — сериализуется через `.value`
  (`item.role.value`), не голым `str()`, иначе в CSV попало бы
  `"UserRole.student"` вместо `"student"` (`class UserRole(str, enum.Enum)`
  наследует `Enum.__str__`, не `str.__str__`).
- Фронтенд: `docs/frontend-admin-users-api-contract.md` обновлён (§0, §1.1,
  `role` в §2/§3/§4, §7, §8) — это контракт для команды Profy-Frontend на
  `role`-поле в существующих ответах и на новый `POST /api/v1/admin/users`.

### Найденные и исправленные data-access gap'ы (в рамках Milestone 1)

При ревью доступов к данным после первой реализации нашлись 4 момента,
все исправлены в этой же ветке:

1. **`scripts/make_admin.py` и `scripts/create_admin_user.py` падали бы** —
   писали напрямую в `user.is_admin = ...`, которая стала read-only property.
   Мой первоначальный grep-чек перед стартом искал только по `app/`/`tests/`
   (по плану), эти ops-скрипты вне обоих — пропустил. Переписаны на
   `role=UserRole.admin/student`, проверены end-to-end на throwaway БД.
2. **Физическая колонка `is_admin` в БД теперь "мёртвая"** — приложение её
   больше не пишет (подтверждено: после смены роли через `make_admin.py`
   колонка `is_admin` в БД осталась `false`). Любой прямой SQL/BI-запрос к
   этой колонке в обход API теперь будет врать — не найдено такого в этом
   репозитории, но стоит проверить внешние аналитические инструменты, если
   они есть.
3. **`GET /api/v1/admin/users` и `/export` не фильтровали по роли** —
   admin/psychologist аккаунты, созданные через §1.1, засоряли бы список
   "учеников" пустыми профилями. Исправлено: новый query-параметр `role`
   (`app/routers/admin.py`, `app/services/admin_service.py`), по умолчанию
   `student` — сохраняет прежнее фактическое поведение (раньше других ролей
   не существовало), явный `?role=admin`/`?role=psychologist` — для
   просмотра сотрудников. Покрыто
   `test_users_list_excludes_staff_accounts_by_default` в
   `tests/integration/test_admin_user_provisioning.py`.
4. **Студенческие роуты не проверяли роль вообще** — `/profile`,
   `/assessment`, `/artifacts`, `/certificates`, `/motivation`,
   `/motivation-pairs`, `/question-pairs`, `/direction-inquiry`, `/result`,
   `/questions`, `/university`, `/roadmap` (все 12, кроме `/auth/me` —
   он намеренно остаётся на `get_current_user`, доступен всем ролям) были
   гейтованы только `get_current_user`, без проверки роли — admin/
   psychologist аккаунт технически мог создать себе Profile и пройти тест.
   Исправлено новой зависимостью `get_current_student_user`
   (`app/dependencies.py`, 403 если `role != student`) — заменяет
   `get_current_user` во всех 12 роутерах, сигнатура не меняется (всё ещё
   возвращает `User`), поэтому остальной код роутеров не тронут. Покрыто
   `tests/integration/test_student_role_gating.py`.

Полный прогон `pytest` после обоих фиксов: 381 passed (было 375 — +6 новых
тестов), те же 8 pre-existing failures, ничего нового не сломано.

### Заметка для будущих миграций на этой ветке

Локальная dev БД на момент реализации имела `alembic_version`, указывающий
на ревизию из чужой (i18n/`dev`) ветки, отсутствующую в `pro-281` — не
существующую в истории этой ветки. Миграция `12cdf8d6ab06` цепляется к
реальному текущему head'у `pro-281` (`f2a9c6e814b7`), проверено через
`alembic heads`/`alembic current` и полный round-trip (`upgrade head` →
`downgrade -1` → `upgrade head`) на чистой throwaway БД, не на
замусоренной shared dev БД. При появлении следующей миграции — всегда
перепроверять `alembic heads` заново, не доверять этому документу.

## Milestone 2 — Доступ психолога к назначенным ученикам (planned)

- Новая модель `app/models/psychologist_assignment.py` —
  `PsychologistStudentAssignment` (`psychologist_id`, `student_id` →
  `users.id`, unique-constraint на пару). Роли участников валидируются на
  уровне сервиса при создании (не в БД).
- Admin CRUD для назначений (`app/routers/admin.py`, тот же
  `get_current_admin_user`): `POST/GET/DELETE
  /api/v1/admin/psychologist-assignments`, сервис
  `app/services/admin_psychologist_service.py`.
- Психолог-роутер `app/routers/psychologist.py` (mount на
  `/api/v1/psychologist`): `app/services/psychologist_service.py` с
  `_require_assigned_student()` — 404 (не 403) при отсутствии назначения,
  тем же паттерном что `_require_profile_id`/`_require_assessment_access`
  (`app/routers/assessment.py:19`).
  - `GET /students` — список назначенных, узкая схема
    `PsychologistStudentListItem`.
  - `GET /students/{id}` — после `_require_assigned_student`, переиспользует
    `admin_service.get_user_detail()`, оборачивает в отдельную
    `PsychologistStudentDetailResponse` (не отдавать `AdminUserDetailResponse`
    как есть).

## Milestone 3 — Заметки психолога (planned)

- Новая модель `app/models/psychologist_note.py` — `PsychologistNote`
  (`psychologist_id`, `student_id`, `content: Text`, без уникальности —
  заметок может быть много).
- Двойная проверка при CRUD: (a) `note.psychologist_id == current_user.id`
  (иначе 404, не 403), (b) создание новой заметки требует активного
  назначения (`_require_assigned_student`) — **soft cutoff**: чтение/
  редактирование/удаление уже существующих заметок разрешено независимо от
  текущего статуса назначения.
- Роуты в `app/routers/psychologist.py`: `POST/GET
  /students/{student_id}/notes`, `PATCH/DELETE /notes/{note_id}`.
- Админский доступ на чтение заметок (для надзора) — не запрошен, вне
  скоупа Milestone 3, добавляется отдельным PR при необходимости.

## Проверка

- `docker compose exec api alembic upgrade head` / `alembic downgrade -1` —
  round-trip после каждой новой миграции.
- `docker compose exec api pytest tests/unit/test_role_permissions.py
  tests/integration/test_admin_user_provisioning.py` — целевые тесты роль-
  инфраструктуры; затем полный `pytest` — не должно быть новых падений
  относительно baseline (8 pre-existing failures, см. Status выше).
- Ручная проверка через `/docs`: `POST /api/v1/admin/users` с
  `role=psychologist`, логин под этим пользователем, `GET
  /api/v1/psychologist/students` — пустой список до назначения, непустой
  после `POST /api/v1/admin/psychologist-assignments` (Milestone 2).
