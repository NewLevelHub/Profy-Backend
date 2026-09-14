# Psychologist assignments API — контракт для фронтенда

**Статус: реализовано на ветках `pro-325` (модель), `pro-326` (admin CRUD),
`pro-327` (psychologist router), контракт и чеклист-тесты — `pro-328`,
актуально на 2026-09-09.** Основано на прямом чтении
`app/routers/admin.py` (блок `/psychologist-assignments`),
`app/routers/psychologist.py`, `app/schemas/admin.py`
(`PsychologistAssignment*`), `app/schemas/psychologist.py`,
`app/services/admin_psychologist_service.py`,
`app/services/psychologist_service.py`.

Фронтенд — отдельный репозиторий (Profy-Frontend). Этот документ — контракт
для двух UI-поверхностей Milestone 2:

1. **Админка** — привязка психолог ↔ ученик.
2. **Кабинет психолога** — список и карточка только *назначенных* учеников.

Сиблинг к `docs/frontend-admin-users-api-contract.md` (провижининг
`admin`/`psychologist` аккаунтов и `role` на `User`). Auth-паттерн тот же
JWT Bearer; отличие — психолог **не** проходит через `/api/v1/admin/*`
(получит 403), для него отдельный префикс `/api/v1/psychologist`.

## 0. Роли и скоуп

| Роль | Admin assignments CRUD | Psychologist students |
|---|---|---|
| `admin` | да (`get_current_admin_user`) | нет → **403** |
| `psychologist` | нет → **403** | да (`require_role(psychologist)`) |
| `student` | нет → **403** | нет → **403** |

Назначение хранится в `psychologist_student_assignments`
(`psychologist_id`, `student_id` → `users.id`, unique на пару). Роли
участников **не** enforced в БД — только в сервисе при `POST` назначения.

**Важная семантика 404 vs 403 у психолога:** если ученик существует, но
не назначен этому психологу (или id вообще чужой) —
`GET /psychologist/students/{id}` возвращает **404** `"Student not found"`,
не 403. Так нельзя зондировать, есть ли ученик в системе. Тот же паттерн,
что `_require_profile_id` / `_require_assessment_access`.

## 1. Эндпоинты (обзор)

| Method | Path | Кто | Назначение |
|---|---|---|---|
| POST | `/api/v1/admin/psychologist-assignments` | admin | создать назначение |
| GET | `/api/v1/admin/psychologist-assignments` | admin | список назначений |
| DELETE | `/api/v1/admin/psychologist-assignments/{assignment_id}` | admin | снять назначение |
| GET | `/api/v1/psychologist/students` | psychologist | список *моих* учеников |
| GET | `/api/v1/psychologist/students/{student_id}` | psychologist | карточка назначенного ученика |

## 2. Admin — создать назначение

```text
POST /api/v1/admin/psychologist-assignments
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "psychologist_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  "student_id": "11111111-2222-3333-4444-555555555555"
}
```

- Оба поля обязательны, UUID.
- `psychologist_id` должен указывать на юзера с `role=psychologist`, иначе
  **400** `{"detail": "psychologist_id must refer to a user with role=psychologist"}`.
- `student_id` — на `role=student`, иначе **400** с аналогичным текстом.
- Юзер не найден → **400** `"Psychologist not found"` / `"Student not found"`.
- Пара уже существует → **400** `"Assignment already exists"`.
- Не-админ (включая psychologist) → **403**.
- Успех → **201**:

```jsonc
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "psychologist_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  "student_id": "11111111-2222-3333-4444-555555555555",
  "created_at": "2026-09-09T10:00:00Z"
}
```

UI: форма «назначить ученика психологу» — два селекта (психологи из
`GET /admin/users?role=psychologist`, ученики из
`GET /admin/users` / default `role=student`). На 400 с «already exists»
показать «уже назначен», не как сетевой сбой.

## 3. Admin — список назначений

```text
GET /api/v1/admin/psychologist-assignments?page=1&limit=20&psychologist_id=<uuid>&student_id=<uuid>
```

- `page` / `limit` — как в остальной админке (1-based, limit 1..100, default 20).
- `psychologist_id` / `student_id` — опциональные фильтры (оба можно сразу).
- Сортировка: `created_at` DESC (новые сверху).

```jsonc
{
  "items": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "psychologist_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
      "student_id": "11111111-2222-3333-4444-555555555555",
      "created_at": "2026-09-09T10:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "limit": 20
}
```

**Нет email/имени в ответе** — только UUID. Для таблицы админке нужно
джойнить с уже загруженным кэшем юзеров или отдельными
`GET /admin/users/{id}` (или держать map id→email после загрузки списков
сотрудников/учеников). Это сознательно узкий payload; обогащение —
задача UI, не бэкенда.

## 4. Admin — удалить назначение

```text
DELETE /api/v1/admin/psychologist-assignments/{assignment_id}
Authorization: Bearer <admin-token>
```

- Успех → **204** без тела.
- Нет такой строки → **404** `"Assignment not found"`.
- Не-админ → **403**.

После удаления психолог **перестаёт** видеть ученика в
`GET /psychologist/students` и получает 404 на карточке. (Заметки
психолога — Milestone 3 / soft cutoff — здесь ещё нет.)

## 5. Psychologist — список учеников

```text
GET /api/v1/psychologist/students
Authorization: Bearer <psychologist-token>
```

- Без пагинации: ответ — **массив**, не `{items,total,...}`.
- Только ученики, назначенные *этому* психологу (из JWT `sub`).
- До назначения → `[]`.
- Не-psychologist → **403** `"Insufficient role"`.

```jsonc
[
  {
    "id": "11111111-2222-3333-4444-555555555555",
    "email": "student@example.com",
    "profile_name": "Arman",          // null, если анкеты ещё нет
    "age_group": "senior",            // null без профиля; иначе junior|middle|senior
    "assigned_at": "2026-09-09T10:00:00Z"
  }
]
```

UI: таблица/список учеников кабинета психолога. Пустое состояние —
«пока нет назначенных учеников» (админ ещё не привязал).

## 6. Psychologist — карточка ученика

```text
GET /api/v1/psychologist/students/{student_id}
Authorization: Bearer <psychologist-token>
```

- Сначала проверка назначения; нет → **404** `"Student not found"`.
- Данные собираются через тот же fetch, что админский
  `get_user_detail`, но ответ — **отдельная** схема
  `PsychologistStudentDetailResponse`: **нет** полей `role` / `is_admin`.
  Не переиспользуйте админский тип ответа на фронте один-в-один.

```jsonc
{
  "id": "11111111-2222-3333-4444-555555555555",
  "email": "student@example.com",
  "is_verified": true,
  "is_active": true,
  "created_at": "2026-08-28T09:20:13Z",
  "profile": { /* ProfileResponse или null */ },
  "artifacts": [ /* ArtifactItem[] */ ],
  "assessments": [
    {
      "id": "...",
      "goal": "university",
      "status": "completed",
      "answered_count": 42,
      "total_questions": 42,
      "created_at": "...",
      "completed_at": "...",
      "has_result": true,
      "has_roadmap": true
    }
  ]
}
```

`profile` — тот же shape, что в student/admin profile API
(`ProfileResponse`: name, age, grade, city, subjects_*, age_group, …).
Полный разбор полей профиля — в существующих profile-контрактах;
здесь важно: `null`, пока ученик не заполнил анкету.

`assessments` — краткие саммари (без полного `analysis_result`). Для
глубокого просмотра результата админка ходит в
`GET /admin/assessments/{id}`; **у психолога такого эндпоинта в M2 нет** —
карточка даёт список тестов и флаги `has_result` / `has_roadmap`. Если
продукту нужен полный отчёт психологу — отдельный тикет поверх M2.

## 7. Типовой happy-path (ручная проверка /docs)

1. Админом: `POST /api/v1/admin/users` с `role=psychologist` (см.
   `frontend-admin-users-api-contract.md` §1.1).
2. Логин под этим психологом → `GET /api/v1/psychologist/students` → `[]`.
3. Админом: `POST /api/v1/admin/psychologist-assignments` с id психолога и
   существующего ученика.
4. Снова `GET /api/v1/psychologist/students` → один элемент; затем
   `GET /api/v1/psychologist/students/{id}` → 200.
5. Без назначения / чужой id → 404; студентским или админским токеном на
   `/psychologist/*` → 403.

Автотесты того же чеклиста:
`tests/integration/test_milestone2_assignments.py` (+ гранулярные
`test_admin_psychologist_assignments.py`, `test_psychologist_students.py`).

## 8. Что сознательно вне скоупа M2

- Psychologist CRUD заметок — Milestone 3 (`PsychologistNote`); контракт:
  `docs/frontend-psychologist-notes-api-contract.md`.
- Полный assessment/report API для психолога.
- Email/имя в admin list назначений (только UUID).
- Пагинация на `GET /psychologist/students`.
