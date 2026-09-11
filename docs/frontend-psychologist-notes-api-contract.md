# Psychologist notes API — контракт для фронтенда

**Статус: реализовано на ветках `pro-329` (модель), `pro-330` (CRUD + soft
cutoff), контракт и чеклист-тесты — `pro-331`, актуально на 2026-09-09.**
Основано на прямом чтении `app/routers/psychologist.py`,
`app/schemas/psychologist.py` (`PsychologistNote*`),
`app/services/psychologist_service.py`, `app/models/psychologist_note.py`.

Фронтенд — отдельный репозиторий (Profy-Frontend). Этот документ — контракт
для **заметок психолога** (Milestone 3). Назначения учеников — сиблинг
`docs/frontend-psychologist-assignments-api-contract.md`. Auth тот же JWT
Bearer + `require_role(psychologist)` на всём `/api/v1/psychologist/*`.

**Админского read/CRUD заметок нет** и в M3 не планируется — не рисуйте
админ-UI для просмотра чужих заметок, эндпоинтов под это нет.

## 0. Soft cutoff (важно для UI)

| Действие | Пока есть назначение | После снятия назначения |
|---|---|---|
| `POST` новая заметка | да | **нет** → **404** `"Student not found"` |
| `GET` список своих заметок | да | **да** (старые остаются) |
| `PATCH` / `DELETE` своей заметки | да | **да** |

Смысл: отвязка ученика от психолога **не стирает историю заметок**, но
блокирует новые. В UI после unassign:

- карточку ученика из `GET /students` вы уже не получите (404 / нет в списке);
- но если у вас сохранён `student_id` и ранее созданные `note_id`, список
  заметок и edit/delete по ним продолжают работать;
- кнопку «Добавить заметку» нужно **прятать/дизейблить**, если ученик больше
  не в `GET /students` (или после 404 на POST показать «ученик больше не
  назначен», не «ошибка сервера»).

Чужая заметка (другого психолога) или несуществующий `note_id` → всегда
**404** `"Note not found"`, никогда **403** — нельзя зондировать чужие id.

## 1. Эндпоинты (обзор)

| Method | Path | Назначение |
|---|---|---|
| POST | `/api/v1/psychologist/students/{student_id}/notes` | создать заметку |
| GET | `/api/v1/psychologist/students/{student_id}/notes` | список *своих* заметок по ученику |
| PATCH | `/api/v1/psychologist/notes/{note_id}` | изменить текст |
| DELETE | `/api/v1/psychologist/notes/{note_id}` | удалить |

Все — только `role=psychologist`. Student / admin → **403**
`"Insufficient role"`.

## 2. Создать заметку

```text
POST /api/v1/psychologist/students/{student_id}/notes
Authorization: Bearer <psychologist-token>
Content-Type: application/json

{"content": "Рекомендовал повторно пройти блок мотивации"}
```

- `content` — обязательная непустая строка (`min_length=1`), иначе **422**.
- Нет активного назначения на этого ученика → **404** `"Student not found"`.
- Успех → **201**:

```jsonc
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "psychologist_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  "student_id": "11111111-2222-3333-4444-555555555555",
  "content": "Рекомендовал повторно пройти блок мотивации",
  "created_at": "2026-09-09T12:00:00Z"
}
```

Заметок на пару психолог↔ученик может быть **много** (нет unique).

## 3. Список заметок по ученику

```text
GET /api/v1/psychologist/students/{student_id}/notes
Authorization: Bearer <psychologist-token>
```

- Без пагинации: ответ — **массив** (не `{items,total}`).
- Только заметки текущего психолога для этого `student_id`.
- Сортировка: `created_at` DESC.
- Soft cutoff: назначение **не** требуется — вернёт старые заметки или `[]`.
- Не-psychologist → **403**.

```jsonc
[
  {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "psychologist_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "student_id": "11111111-2222-3333-4444-555555555555",
    "content": "…",
    "created_at": "2026-09-09T12:00:00Z"
  }
]
```

UI: тред/список заметок на карточке ученика. Пустой массив — нормальное
состояние «пока нет заметок».

## 4. Изменить заметку

```text
PATCH /api/v1/psychologist/notes/{note_id}
Authorization: Bearer <psychologist-token>
Content-Type: application/json

{"content": "Обновлённый текст"}
```

- `content` — обязателен, `min_length=1` → иначе **422**.
- Чужой / несуществующий id → **404** `"Note not found"`.
- Soft cutoff: работает и после снятия назначения.
- Успех → **200**, тот же shape, что у create.

`updated_at` в модели **нет** — в ответе только `created_at`. Если нужна
дата правки — отдельный тикет/миграция.

## 5. Удалить заметку

```text
DELETE /api/v1/psychologist/notes/{note_id}
Authorization: Bearer <psychologist-token>
```

- Успех → **204** без тела.
- Чужой / нет такой → **404** `"Note not found"`.
- Soft cutoff: удаление старых заметок после unassign разрешено.

## 6. Типовой happy-path (+ soft cutoff)

1. Админ назначает ученика психологу
   (`POST /api/v1/admin/psychologist-assignments`, см. контракт назначений).
2. Психолог: `POST .../students/{id}/notes` → 201; `GET .../notes` → массив.
3. `PATCH` / `DELETE` по `note_id` → 200 / 204.
4. Админ снимает назначение (`DELETE .../psychologist-assignments/{id}`).
5. Психолог: новый `POST .../notes` → **404**; `GET` / `PATCH` / `DELETE` по
   старой заметке → по-прежнему ок.

Автотесты: `tests/integration/test_psychologist_notes.py`, чеклист
`tests/integration/test_milestone3_notes.py`.

## 7. Что сознательно вне скоупа

- Admin read / moderation заметок.
- `updated_at` на заметке.
- Пагинация списка.
- Заметки в ответе `GET /students/{id}` (карточка ученика) — отдельный
  запрос на `/notes`.
