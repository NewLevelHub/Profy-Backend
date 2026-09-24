# Psychologist assignments API — контракт для фронтенда

**Статус: реализовано на ветках `pro-325` (модель), `pro-326` (admin CRUD),
`pro-327` (psychologist router), контракт и чеклист-тесты — `pro-328`,
актуально на 2026-09-09.** Основано на прямом чтении
`app/routers/psychologist.py`, `app/schemas/psychologist.py`,
`app/services/psychologist_service.py`.

> **PRO-425 (2026-09-24): admin CRUD назначений удалён.** Эндпоинты
> `/api/v1/admin/psychologist-assignments` (POST/GET/DELETE),
> `admin_psychologist_service` и схемы `PsychologistAssignment*` убраны —
> фронтенд их не вызывал. Назначение теперь создаёт сам психолог
> (self-claim): `GET /api/v1/psychologist/students/available` →
> `POST /api/v1/psychologist/students/{student_id}/claim`. Разделы 2–4 ниже
> оставлены заголовками только чтобы не ломать ссылки.

Фронтенд — отдельный репозиторий (Profy-Frontend). Этот документ — контракт
для двух UI-поверхностей Milestone 2:

1. ~~**Админка** — привязка психолог ↔ ученик.~~ Удалено в PRO-425, см. выше.
2. **Кабинет психолога** — self-claim ученика, список и карточка только
   *назначенных* учеников.

Сиблинг к `docs/frontend-admin-users-api-contract.md` (провижининг
`admin`/`psychologist` аккаунтов и `role` на `User`). Auth-паттерн тот же
JWT Bearer; отличие — психолог **не** проходит через `/api/v1/admin/*`
(получит 403), для него отдельный префикс `/api/v1/psychologist`.

## 0. Роли и скоуп

| Роль | Psychologist students (включая claim) |
|---|---|
| `admin` | нет → **403** |
| `psychologist` | да (`require_role(psychologist)`) |
| `student` | нет → **403** |

Назначение хранится в `psychologist_student_assignments`
(`psychologist_id`, `student_id` → `users.id`, unique на пару). Роли
участников **не** enforced в БД — только в сервисе при claim
(`psychologist_service.claim_student`).

**Важная семантика 404 vs 403 у психолога:** если ученик существует, но
не назначен этому психологу (или id вообще чужой) —
`GET /psychologist/students/{id}` возвращает **404** `"Student not found"`,
не 403. Так нельзя зондировать, есть ли ученик в системе. Тот же паттерн,
что `_require_profile_id` / `_require_assessment_access`.

## 1. Эндпоинты (обзор)

| Method | Path | Кто | Назначение |
|---|---|---|---|
| GET | `/api/v1/psychologist/students/available` | psychologist | пул учеников, которых можно взять |
| POST | `/api/v1/psychologist/students/{student_id}/claim` | psychologist | взять ученика (создаёт назначение), **201** |
| GET | `/api/v1/psychologist/students` | psychologist | список *моих* учеников |
| GET | `/api/v1/psychologist/students/{student_id}` | psychologist | карточка назначенного ученика |

## 2–4. Admin — создать / список / удалить назначение

Удалено в PRO-425 (см. статус в начале документа). Снятия назначения через
API сейчас нет.

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
«пока нет назначенных учеников» (психолог ещё никого не взял через claim).

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
      "has_result": true
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
карточка даёт список тестов и флаг `has_result`. Если
продукту нужен полный отчёт психологу — отдельный тикет поверх M2.

## 7. Типовой happy-path (ручная проверка /docs)

1. Админом: `POST /api/v1/admin/users` с `role=psychologist` (см.
   `frontend-admin-users-api-contract.md` §1.1).
2. Логин под этим психологом → `GET /api/v1/psychologist/students` → `[]`.
3. Психологом: `GET /api/v1/psychologist/students/available`, затем
   `POST /api/v1/psychologist/students/{id}/claim` для одного из учеников.
4. Снова `GET /api/v1/psychologist/students` → один элемент; затем
   `GET /api/v1/psychologist/students/{id}` → 200.
5. Без назначения / чужой id → 404; студентским или админским токеном на
   `/psychologist/*` → 403.

Автотесты того же чеклиста: `tests/integration/test_psychologist_students.py`
(назначение в тестах создаётся напрямую в БД через
`tests/integration/review_helpers.assign`).

## 8. Что сознательно вне скоупа M2

- Psychologist CRUD заметок — Milestone 3 (`PsychologistNote`); контракт:
  `docs/frontend-psychologist-notes-api-contract.md`.
- Полный assessment/report API для психолога.
- Пагинация на `GET /psychologist/students`.
