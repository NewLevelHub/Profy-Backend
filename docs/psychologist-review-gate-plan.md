# Проверка результата психологом перед публикацией ученику — план

## Status: Implemented on `pro-337` (2026-09-14)

Реализовано целиком (§1–§6), контракт для фронта —
`docs/frontend-psychologist-review-api-contract.md`. Отличия от текста ниже:
`build_report()` сразу проставляет `pending_review` (шаги 1 и 3 раскатки §7
сделаны в одной ветке — при деплое фронт с поддержкой pending-конверта
должен выйти не позже бэкенда); PATCH дополнительно отклоняет (`422`) коды
`strengths`/`weaknesses`, которых нет в профиле результата, и `careers` не
той формы; `personality_notes` правится, но ученику не виден — блок «Твой
характер» собирается из шкал. Исходный текст плана сохранён ниже.

Ничего из описанного ниже ещё не реализовано в коде — ни модели, ни
миграции, ни эндпоинты. Этот документ фиксирует согласованный дизайн,
чтобы реализация (отдельная будущая работа) шла по одному плану и не
разъезжалась с параллельным фронтенд-документом
`Profy-Frontend/docs/psychologist-review-frontend-plan.md`, с которым этот
файл должен совпадать по форме `ResultPendingReviewResponse` дословно.

## Context

Сегодня `AnalysisResult` не имеет вообще никакого поля состояния/видимости
(`app/models/analysis_result.py`) — как только `report_service.build_report()`
вставляет строку, она немедленно доступна ученику через `GET
/api/v1/result/{assessment_id}` (единственная проверка в
`app/routers/result.py::_require_assessment_access` — владение, не
состояние). Психолог сегодня видит только сводку по assessment'у ученика
(`goal`/`status`/`has_result`/`has_roadmap` — булевы флаги, без содержимого,
`app/routers/psychologist.py::get_student` →
`PsychologistStudentDetailResponse`), и в
`docs/user-roles-integration-plan.md` "полный assessment/report API для
психолога" прямо назван будущим milestone, вне скоупа Milestone 1–3.

Продуктовое требование: после завершения теста результат не должен сразу
попадать к ученику. Он должен сначала появиться у назначенного психолога
(`PsychologistStudentAssignment`, уже реализовано в Milestone 2), который
может скорректировать содержание, и только после явной публикации —
результат становится виден ученику и остаётся сохранённым в его профиле.

Этот документ — Milestone 4 плана ролей, продолжающий нумерацию
`docs/user-roles-integration-plan.md` (Milestone 1–3 done).

## Продуктовые решения (предлагаются к фиксации)

1. **Два состояния, не три**: `pending_review` → `published`. Запрос
   описывает одно действие психолога ("корректирует и после показывает"),
   без отдельного шага "одобрено, но не опубликовано". `reviewed_by`/
   `reviewed_at` дают сигнал "кто-то смотрел/редактировал" без отдельного
   enum-значения. Если позже понадобится третье состояние — добавляется без
   миграции данных (просто новое значение enum + новая ветка в сервисе).
2. **Правка на месте, не draft-колонки**: контентные поля `AnalysisResult`
   правятся напрямую психологом, с записью в отдельную таблицу аудита
   (`analysis_result_review_edits`), а не дублируются в `*_draft`-колонки.
   Обоснование: единственный редактор на строку до момента публикации —
   конкурентного редактирования, от которого защищают draft-схемы, здесь
   нет.
3. **Генерация никогда не блокируется отсутствием назначенного
   психолога.** Строка создаётся как `pending_review` в любом случае;
   видимость в очереди психолога зависит от `PsychologistStudentAssignment`
   "вживую" (не снапшотится на `AnalysisResult`), поэтому назначение задним
   числом само подтягивает уже сгенерированный результат в очередь.
4. **Публикация — необратимое действие** в рамках этого milestone: правка
   после публикации не поддерживается (`409`). Если продукту понадобится
   "открыть на редактирование повторно" — отдельный тикет.

## 1. Модель данных

**Файл:** `app/models/analysis_result.py`

```python
class ReviewStatus(str, enum.Enum):
    pending_review = "pending_review"
    published = "published"
```

Новые колонки на `AnalysisResult`:

| Колонка | Тип | Nullable | Назначение |
|---|---|---|---|
| `review_status` | `Enum(ReviewStatus, name="analysis_result_review_status_enum")` | нет, `default=pending_review`, `server_default="pending_review"` | текущее состояние |
| `reviewed_by` | `UUID` FK `users.id`, `ondelete="SET NULL"` | да | кто последним правил контент |
| `reviewed_at` | `DateTime(timezone=True)` | да | когда последний раз правили |
| `published_by` | `UUID` FK `users.id`, `ondelete="SET NULL"` | да | кто опубликовал |
| `published_at` | `DateTime(timezone=True)` | да | когда опубликовано |

**Новый файл** `app/models/analysis_result_review_edit.py`:

```python
class AnalysisResultReviewEdit(Base):
    __tablename__ = "analysis_result_review_edits"
    id: UUID primary key, default=uuid4
    analysis_result_id: UUID FK analysis_results.id, ondelete="CASCADE", index=True
    editor_id: UUID FK users.id, ondelete="SET NULL", nullable
    edited_at: DateTime(timezone=True), server_default=now()
    changed_fields: JSONB  # {"field": {"old": ..., "new": ...}, ...}
```

Одна запись на каждый успешный `PATCH` (§3.3) — история правок без
дублирования схемы контента.

### Alembic-миграция

В репозитории 60+ файлов миграций с несколькими параллельными head (см.
`CLAUDE.md`: "Run `alembic heads` to find the real current head... don't
infer it by reading filenames"). Перед созданием миграции этого milestone
**обязательно** выполнить `alembic heads` в реальном окружении
реализации — не полагаться на список head'ов, зафиксированный в этом
документе на момент его написания (`0043`, `7db53544fd3d`, `0042`,
`a1c5f39be702` — устареет). Если head несколько — сначала merge-миграция
(прецеденты в репозитории: `e366cb88e71f_merge_heads.py`).

Миграция `xxxx_add_review_status_to_analysis_results.py` должна:

1. Создать `analysis_result_review_edits` (FK, index на
   `analysis_result_id`).
2. Добавить 5 колонок из таблицы выше на `analysis_results`.
3. **Бэкофилл** (критично для существующих пользователей):
   ```sql
   UPDATE analysis_results
   SET review_status = 'published', published_at = created_at
   WHERE review_status = 'pending_review';
   ```
   Каждая строка, созданная до этой миграции, уже была показана ученику —
   миграция не должна задним числом её скрыть.
4. Обратимый `downgrade()`: drop колонок, drop таблицы, drop enum-типа.
5. Round-trip (`alembic upgrade head` → `downgrade -1` → `upgrade head`) на
   чистой throwaway БД перед мержем — по конвенции, зафиксированной в
   `docs/user-roles-integration-plan.md` ("Заметка для будущих миграций").

## 2. Флоу генерации и выдачи результата (студенческая сторона)

**Файл:** `app/services/report_service.py`

- `build_report()`: при вставке новой строки `AnalysisResult` явно
  проставлять `review_status=ReviewStatus.pending_review` (не полагаться
  только на default колонки — рядом с уже существующей явной установкой
  `report_version=2`).
- Новая функция `get_review_status(assessment_id, db) -> ReviewStatus | None`
  — простой `select(AnalysisResult.review_status).where(...)`, без похода в
  кэш. Единственный источник истины для гейта в роутере (§2.1).
- **Кэш**: во всех местах, где текущий код пишет в Redis
  (`report:v2:{assessment_id}`, 24ч TTL) — и в `build_report()`, и в
  `get_report()` — добавить проверку `review_status == ReviewStatus.published`
  перед `_cache_set(...)`. Непопубликованный отчёт никогда не должен попасть
  в кэш, из которого читает студенческий `GET`.
- После `db.commit()`/`db.refresh()` для **новой** строки (не для двух
  веток "строка уже существует", не для fallback-ветки `IntegrityError`) —
  best-effort уведомление назначенному психологу (§4), в
  `try/except Exception: logger.exception(...)`, чтобы сбой почты не мог
  сломать генерацию отчёта.
- `Assessment.status` (`in_progress`/`completed`) не трогаем — эта
  колонка используется другими потребителями (roadmap, goal overlay,
  admin-сводки) и означает "тест пройден", а не "результат виден" —
  смешивать эти два смысла в одном enum не нужно.

**Файл:** `app/routers/result.py`

Новая схема в `app/schemas/result_v2.py`:

```python
class ResultPendingReviewResponse(BaseModel):
    status: Literal["pending_review"] = "pending_review"
    assessment_id: uuid.UUID
    model_config = {"extra": "forbid"}
```

- `response_model` у `POST /generate` и `GET /{assessment_id}` расширяется
  до `ResultV2Schema | ResultPendingReviewResponse`.
- `POST /generate`: вызвать `build_report()` как сегодня (идемпотентно), затем
  `get_review_status()`; если `pending_review` — вернуть pending-конверт;
  если `published` (пре-миграционная строка либо повторная генерация уже
  опубликованного отчёта) — вернуть полную форму как сегодня.
- `GET /{assessment_id}`: вызвать `get_review_status()` **до** любого похода
  в `get_report()`/кэш. `None` → существующий 404. `pending_review` →
  pending-конверт, `get_report()` не вызывается вовсе. `published` →
  `get_report()` как сегодня.
- **Почему `200` с отдельной формой, а не `403`/`404`**: фронтенд
  (`useResults.ts`) уже трактует `403` на этом эндпоинте как признак чужой/
  устаревшей сессии и сбрасывает весь стейт ассесмента —
  переиспользование этого кода для легитимного "ещё не опубликовано"
  сломало бы этот путь. Отдельное поле `status` в `200`-ответе даёт фронту
  чистую точку ветвления, не задевая существующую обработку 403.

## 3. Новые эндпоинты психолога

**Файлы:** `app/routers/psychologist.py`, `app/services/psychologist_service.py`,
новый `app/schemas/psychologist_result.py`.

Все — под существующим `require_role(UserRole.psychologist)` +
`_require_assigned_student()` (404, не 403, при отсутствии назначения —
переиспользуется существующий хелпер).

### 3.1 `GET /api/v1/psychologist/reviews`

Очередь всех `pending_review` результатов среди учеников, назначенных
текущему психологу.

```jsonc
[
  {
    "assessment_id": "uuid",
    "student_id": "uuid",
    "student_name": "Имя ученика или null",
    "student_email": "student@example.com",
    "age_group": "middle",
    "goal": "career_direction",
    "generated_at": "2026-09-10T08:00:00Z",
    "reviewed_at": null
  }
]
```

### 3.2 `GET /api/v1/psychologist/students/{student_id}/results/{assessment_id}`

Полное содержимое отчёта — сырые и нарративные поля (`big_five`,
`motivation`, `personality_notes` и т.д.), в отличие от урезанной
студенческой `ResultV2Schema`. Доступен для любого `review_status`
(психолог может открыть уже опубликованный результат для просмотра,
только не для правки — см. §3.3).

```jsonc
{
  "assessment_id": "uuid",
  "review_status": "pending_review",
  "reviewed_by": null,
  "reviewed_at": null,
  "published_by": null,
  "published_at": null,
  "summary": "...",
  "careers": [ /* ... */ ],
  "strengths": ["R", "I"],
  "weaknesses": ["C"],
  "development_plan": { "reinforce": [], "compensate": [] },
  "big_five": { "N": 32.0 },
  "thinking_style": { "creative_think": 70 },
  "strength_cards": [ { "title": "...", "description": "..." } ],
  "thinking_style_notes": [ { "title": "...", "description": "..." } ],
  "final_analysis": "...",
  "personality_notes": { "...": "..." },
  "motivation_highlights": ["..."],
  "created_at": "2026-09-10T08:00:00Z"
}
```

### 3.3 `PATCH /api/v1/psychologist/students/{student_id}/results/{assessment_id}`

Частичная правка контентных полей: `summary`, `careers`, `strengths`,
`weaknesses`, `strength_cards`, `thinking_style_notes`, `final_analysis`,
`personality_notes`, `motivation_highlights`. Намеренно исключены из
разрешённых к правке: `profile`, `code`, `meta`, `report_version`,
`assessment_id` — сырые входные данные, от которых зависят другие пайплайны
(roadmap, goal overlay).

- `409`, если `review_status != pending_review` — правка опубликованного
  результата вне скоупа этого milestone.
- При успехе: применить переданные поля, проставить `reviewed_by`/
  `reviewed_at`, записать `AnalysisResultReviewEdit` (§1) с diff
  изменённых полей, точечно удалить Redis-ключ
  `report:v2:{assessment_id}` (defensive — см. §5), закоммитить.

### 3.4 `POST /api/v1/psychologist/students/{student_id}/results/{assessment_id}/publish`

Необратимый переход `pending_review` → `published`.

- `409`, если уже `published`.
- При успехе: `review_status=published`, `published_by`, `published_at`;
  если `reviewed_by`/`reviewed_at` ещё не проставлены (психолог
  опубликовал без правок) — проставить их тоже. Удалить кэш-ключ. После
  коммита — best-effort письмо ученику (§4).

Эти четыре эндпоинта читают/пишут `AnalysisResult` напрямую, **в обход**
`report_service.build_report/get_report/_shape_response` — психологу нужны
поля, которые `_shape_response` намеренно скрывает от ученика, и так
review-флоу физически не может прогреть студенческий кэш неодобренным
контентом (см. §5).

### 3.5 Сервисные методы (`psychologist_service.py`)

По образцу существующих `_require_assigned_student`/`_require_own_note`:

- `_require_result_for_student(db, *, student_id, assessment_id) -> AnalysisResult`
  — join `AnalysisResult → Assessment → Profile → User`, `ValueError`
  ("Result not found") → 404 в роутере, если ассесмент не принадлежит
  `student_id`.
- `list_pending_reviews(db, psychologist_id)`
- `get_result_for_review(db, *, psychologist_id, student_id, assessment_id)`
- `update_result_content(db, *, psychologist_id, student_id, assessment_id, patch)`
  — бросает новый `ResultAlreadyPublishedError(Exception)` → 409 в роутере
  (тот же паттерн catch, что уже есть для `ValueError` → 404 на notes-роутах).
- `publish_result(db, *, psychologist_id, student_id, assessment_id)` —
  тот же `ResultAlreadyPublishedError` при повторном вызове.

### 3.6 Обновление существующих summary-эндпоинтов

`admin_service.get_user_detail()` сегодня строит только `has_result: bool`
(множество `assessment_id`, у которых есть строка `AnalysisResult`).
Изменить на выборку `(AnalysisResult.assessment_id, AnalysisResult.review_status)`
и прокинуть новое поле `review_status: str | None = None` в
`PsychologistAssessmentSummary` (`app/schemas/psychologist.py`) через
`_to_psychologist_detail()` в `psychologist_service.py`. Это то, что
позволит `PsychologistStudentDetailPage` (фронтенд) показывать "на
проверке"/"опубликовано" вместо текущего бинарного `has_result`, и что
обесценивает существующий в коде фронта комментарий про "полный отчёт
психологу в этом релизе не отдаётся" — его нужно будет убрать при
реализации.

`AdminAnalysisResultResponse` (`app/schemas/admin_result.py`) — добавить
все 5 новых полей для безусловного admin-доступа (admin не гейтуется
`review_status`, только получает видимость новых полей).

## 4. Обработка ученика без назначенного психолога

Генерация никогда не блокируется (§0.3). `GET /psychologist/reviews`
join'ится через `PsychologistStudentAssignment` "вживую" — назначение
психолога после генерации автоматически подтягивает уже существующий
`pending_review` результат в очередь, без дополнительного кода.

Требуется небольшая admin-заглушка, чтобы неназначенный ученик не завис
навсегда без отчёта: `GET /api/v1/admin/psychologist-reviews/unassigned`
(новый роут в `app/routers/admin.py` + сервис, например
`app/services/admin_psychologist_service.py`) — список `pending_review`
результатов, у чьих студентов нет ни одной активной
`PsychologistStudentAssignment`. Тот же экшен публикации, что и у
психолога (`publish_result` с `published_by=admin.id`), доступен админу
для ручного разбора этой очереди.

## 5. Уведомления

**Файл:** `app/services/email_service.py`

Две новые функции по образцу существующих (`send_verification_email`,
`_load_template` + `resend.Emails.send` через `asyncio.to_thread`), но с
одним отличием: **никогда не бросают исключение** — это fire-and-forget на
критичном пути (генерация, публикация), не OTP-флоу, где ошибка должна
доходить до вызывающего.

```python
async def send_review_pending_email(to: str, student_name: str) -> None:
    """Психологу — новый отчёт ждёт проверки. Best-effort, никогда не raises."""

async def send_result_published_email(to: str, student_name: str) -> None:
    """Ученику — результат опубликован. Best-effort, никогда не raises."""
```

Новые шаблоны `app/templates/email/review_pending.html` и
`result_published.html` — копия HTML-структуры существующего
`verification.html` (та же inline-styled таблица, `lang="ru"`, тот же
цвет фона).

Точки вызова: `send_review_pending_email` — из `build_report()` сразу
после коммита новой строки (§2); `send_result_published_email` — из
`publish_result()` после коммита (§3.4).

## 6. Кэш — сводка

1. `report_service._cache_set` (3 места в `build_report`, 1 в `get_report`)
   — гейтить на `review_status == published`.
2. `GET /{assessment_id}` проверяет `get_review_status()` до любого похода
   в `get_report()`/кэш — пока `pending_review`, кэш вообще не
   затрагивается.
3. Психологические review/edit-эндпоинты (§3) читают/пишут `AnalysisResult`
   напрямую, не через `report_service` — не могут случайно прогреть
   студенческий кэш.
4. `update_result_content()` и `publish_result()` дополнительно (defensive)
   удаляют Redis-ключ `report:v2:{assessment_id}` после коммита — на
   случай, если пункты 1–3 когда-нибудь будут обойдены будущим кодом;
   следующий студенческий `GET` после публикации сам прогреет кэш заново.

## 7. Порядок раскатки

Фича-флагов в проекте нет — вместо них поэтапный, обратно совместимый
порядок работы с фронтендом (полная последовательность — в
`docs/psychologist-review-frontend-plan.md`, §6):

1. **Миграция без смены поведения**: добавить колонки/таблицу + бэкофилл,
   но `build_report()` пока продолжает проставлять `review_status=published`.
   Нулевой риск, проверяет только миграцию.
2. Дождаться, пока фронтенд задеплоит терпимую к pending-конверту версию
   (см. фронтенд-документ, шаг 2 его rollout).
3. **Переключение поведения**: `build_report()` начинает проставлять
   `pending_review`, `result.py` включает гейт, кэш — с проверкой
   публикации.
4. Эндпоинты и очередь психолога (§3) — можно деплоить вместе с шагом 3
   или сразу следом, чтобы очередь не копилась без интерфейса для разбора.
5. Уведомления (§5) и admin-заглушка (§4) — добавляются последними,
   аддитивно.

## 8. Что нужно будет обновить при реализации (не в этой итерации)

- `docs/frontend-result-api-contract.md` — добавить секцию про
  `ResultPendingReviewResponse` (сейчас документ описывает только
  финальную/опубликованную форму, со статусом "реализовано и живёт в
  проде" — редактировать его нужно одновременно с кодом, не раньше).
- Новый `docs/frontend-psychologist-review-api-contract.md` — по
  конвенции именования `frontend-psychologist-{assignments,notes}-api-contract.md`,
  с точными request/response JSON для §3.1–3.4.
- `docs/user-roles-integration-plan.md` — добавить `## Milestone 4 —
  Проверка и публикация отчёта психологом (done)` по образцу Milestone
  1–3, и закрыть строку про "полный assessment/report API для психолога"
  как выполненную.

## Проверка (при реализации)

- `docker compose exec api alembic upgrade head` / `alembic downgrade -1` —
  round-trip, бэкофилл не скрывает существующие результаты.
- Новые `tests/integration/test_result_review_gate.py` (генерация →
  `pending_review`, студенческие `GET`/`POST /generate` отдают конверт,
  публикация открывает полный отчёт, кэш не отдаёт неопубликованный
  контент) и `test_psychologist_review.py` (очередь по назначению, PATCH/
  publish happy path, 409 на повторной публикации/правке после публикации,
  аудит-запись создаётся).
- Ручная проверка через `/docs`: завершить тест учеником → `GET /result`
  отдаёт `{"status": "pending_review"}` → психолог видит в
  `GET /psychologist/reviews` → правит через `PATCH` → публикует → ученик
  получает полный отчёт по `GET /result/{assessment_id}`.
