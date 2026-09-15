# Psychologist review API — контракт для фронтенда

**Статус: реализовано на ветке `pro-337`, актуально на 2026-09-14.**
Основано на прямом чтении `app/routers/psychologist.py`,
`app/routers/result.py`, `app/routers/admin.py`,
`app/schemas/psychologist_result.py`, `app/schemas/result_v2.py`
(`ResultPendingReviewResponse`), `app/services/psychologist_service.py`,
`app/models/analysis_result.py` (`ReviewStatus`), миграция `b7e2d4a91c3f`.
Дизайн и обоснования — `docs/psychologist-review-gate-plan.md`
(Milestone 4 плана ролей).

Сиблинги: `docs/frontend-psychologist-assignments-api-contract.md`
(назначения), `docs/frontend-psychologist-notes-api-contract.md` (заметки).
Auth тот же JWT Bearer + `require_role(psychologist)` на всём
`/api/v1/psychologist/*`.

## 0. Флоу

1. Ученик завершает тест → `POST /result/generate` создаёт отчёт в состоянии
   `pending_review` и отвечает **pending-конвертом** (§1), не отчётом.
2. Всем психологам, назначенным ученику, уходит письмо (best-effort).
3. Психолог видит отчёт в очереди `GET /psychologist/reviews`, открывает,
   правит (`PATCH`) и публикует (`POST .../publish`).
4. После публикации `GET /result/{id}` отдаёт ученику полный отчёт, ученику
   уходит письмо. Публикация необратима, правка после неё — `409`.

Два состояния, без промежуточного «одобрено»:

| `review_status` | Ученик видит | Психолог может править |
|---|---|---|
| `pending_review` | pending-конверт | да |
| `published` | полный отчёт | нет (`409`) |

Отчёты, созданные до миграции, помечены `published` (бэкофилл) — у
существующих учеников ничего не пропало.

## 1. Студенческая сторона — pending-конверт

`POST /api/v1/result/generate` и `GET /api/v1/result/{assessment_id}` теперь
отвечают **одной из двух** форм, обе с кодом `200`:

```jsonc
// пока отчёт не опубликован
{ "status": "pending_review", "assessment_id": "uuid" }

// после публикации — прежняя v2-форма без изменений
{ "report_version": 2, "interest_instrument": "riasec", ... }
```

Ветвиться — по полю `status === "pending_review"`, до проверки
`report_version`/`interest_instrument`. Почему `200`, а не `403`/`404`: `403`
на этом эндпоинте фронт уже трактует как чужую сессию и сбрасывает стейт.
Коды ошибок не изменились: `403` — чужой assessment, `404` — отчёта ещё нет,
`409` — тест не завершён. Pending-ответ никогда не кэшируется.

## 2. Эндпоинты психолога

| Method | Path | Назначение |
|---|---|---|
| GET | `/api/v1/psychologist/reviews` | очередь неопубликованных отчётов своих учеников |
| GET | `/api/v1/psychologist/students/{student_id}/results/{assessment_id}` | полный отчёт для проверки |
| PATCH | `/api/v1/psychologist/students/{student_id}/results/{assessment_id}` | правка содержимого |
| POST | `/api/v1/psychologist/students/{student_id}/results/{assessment_id}/publish` | публикация |

Все — только `role=psychologist` (student / admin → `403`). Нет назначения на
ученика, чужой/несуществующий `assessment_id` → `404` (`"Student not found"` /
`"Result not found"`), никогда `403`.

### 2.1 `GET /reviews`

Только `pending_review`, только ученики с активным назначением на текущего
психолога, старые сверху. Назначение, сделанное после генерации, подтягивает
уже готовый отчёт в очередь.

```jsonc
[
  {
    "assessment_id": "uuid",
    "student_id": "uuid",
    "student_name": "Айгерим",        // null, если имени в профиле нет
    "student_email": "student@example.com",
    "age_group": "senior",            // junior | middle | senior | null
    "goal": "explore",
    "generated_at": "2026-09-14T08:00:00Z",
    "reviewed_at": null               // не null — психолог уже сохранял правки
  }
]
```

### 2.2 `GET /students/{student_id}/results/{assessment_id}`

Доступен для любого `review_status` (опубликованный — только на чтение).

```jsonc
{
  "assessment_id": "uuid",
  "review_status": "pending_review",
  "reviewed_by": null, "reviewed_at": null,
  "published_by": null, "published_at": null,
  "summary": "...",
  "careers": [
    { "slug": "...", "name": "...", "holland_code": "RIA", "match_score": 82,
      "description": "...", "professions": [], "skills_needed": [],
      "subjects_to_develop": [], "first_steps": [] }
  ],
  "strengths": ["R", "I"],
  "weaknesses": ["C"],
  "development_plan": { "reinforce": [], "compensate": [] },
  "big_five": { "N": 32.0 },
  "thinking_style": { "creative_think": 70.0 },
  "strength_cards": [ { "title": "...", "description": "..." } ],
  "thinking_style_notes": [ { "title": "...", "description": "..." } ],
  "final_analysis": "...",
  "personality_notes": { "openness": "..." },
  "motivation_highlights": ["..."],
  "created_at": "2026-09-14T08:00:00Z"
}
```

### 2.3 `PATCH /students/{student_id}/results/{assessment_id}`

Частичная правка: применяются только переданные поля, ответ — полная форма
§2.2. Разрешены: `summary`, `careers`, `strengths`, `weaknesses`,
`strength_cards`, `thinking_style_notes`, `final_analysis`,
`personality_notes`, `motivation_highlights`. Любое другое поле → `422`.

Правила валидации (`422`):

- `summary`, `final_analysis` — непустые строки; `null` для любого поля
  запрещён (не передавайте поле, если не меняете его).
- `strength_cards` / `thinking_style_notes` — `{title, description}`, оба
  непустые, без лишних ключей.
- `careers` — не больше 10, каждый элемент ровно в форме §2.2 (все 9 ключей).
- `strengths` / `weaknesses` — только коды, которые есть в профиле этого
  результата (для RIASEC — буквы `R I A S E C`).

Что увидит ученик после публикации:

| Поле | Попадает в отчёт ученика |
|---|---|
| `summary`, `final_analysis`, `strength_cards`, `thinking_style_notes`, `motivation_highlights` | да, как есть |
| `careers` | порядок, состав и `description`; `why`/`tier` пересчитываются |
| `strengths` | влияет на `why` у направлений |
| `personality_notes` | **нет** — блок «Твой характер» собирается из шкал Big Five |

Успешный PATCH проставляет `reviewed_by`/`reviewed_at` и, если что-то
реально изменилось, пишет запись в `analysis_result_review_edits` (история
`{field: {old, new}}`). Уже опубликованный отчёт → `409`
`"Result is already published"`.

### 2.4 `POST /students/{student_id}/results/{assessment_id}/publish`

Тело — `{}`. Ответ — форма §2.2 с `review_status: "published"`,
`published_by`, `published_at`; если правок не было, `reviewed_by`/
`reviewed_at` тоже проставляются. Повторная публикация → `409`.

### 2.5 Карточка ученика

`GET /api/v1/psychologist/students/{id}` — у каждого элемента `assessments[]`
новое поле `review_status: "pending_review" | "published" | null` (`null` —
отчёта ещё нет). `has_result` оставлен как был.

## 3. Админ

- `GET /api/v1/admin/psychologist-reviews/unassigned` — неопубликованные
  отчёты учеников без единого назначения (форма элементов — §2.1). Без этой
  очереди такие отчёты никто бы не опубликовал.
- `POST /api/v1/admin/psychologist-reviews/{assessment_id}/publish` — та же
  публикация от имени админа (`published_by` = id админа), без проверки
  назначений. `404` / `409` — как у психолога.
- `AdminAnalysisResultResponse` (детали assessment в админке) получил поля
  `review_status`, `reviewed_by`, `reviewed_at`, `published_by`,
  `published_at`. Доступ админа статусом не ограничивается.

## 4. Уведомления

Письма через Resend, fire-and-forget: ошибка отправки только логируется и не
влияет на ответ API. Без `RESEND_API_KEY` письма не отправляются (warning в
логе).

- `review_pending.html` — психологам ученика, один раз при создании отчёта.
- `result_published.html` — ученику после публикации.
