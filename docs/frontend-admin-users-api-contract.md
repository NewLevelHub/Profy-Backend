# Admin Users/Assessments API — контракт для фронтенда

**Статус: реализовано на ветке `pro-226`, актуально на 2026-09-02.**
Основано на прямом чтении `app/routers/admin.py`, `app/schemas/admin.py`,
`app/services/admin_service.py`, `app/services/admin_export_service.py`.

Фронтенд — отдельный репозиторий (Profy-Frontend), этот документ — контракт
для его команды: как получить список юзеров с их результатами тестов,
детали конкретного теста и как выгрузить всё это в CSV. Сиблинг-документ к
`docs/frontend-admin-university-api-contract.md` и
`docs/frontend-admin-questions-api-contract.md` — доступ (JWT + `is_admin`)
устроен идентично, см. §1 университетского контракта, не дублирую здесь.

**Важно:** часть этого API (список юзеров с `riasec`/`big_five` в таблице,
детали одного теста с полным `analysis_result`) уже существовала в бэкенде
раньше — этот документ первый раз её описывает для фронтенда. Новое в этой
задаче — фильтры/2 колонки в списке юзеров и 2 CSV-эндпоинта.

## 1. Эндпоинты (обзор)

| Method | Path | Назначение |
|---|---|---|
| GET | `/api/v1/admin/users` | список юзеров + сырые результаты последнего теста |
| GET | `/api/v1/admin/users/export` | тот же список, без пагинации, в CSV |
| GET | `/api/v1/admin/users/{id}` | детали юзера: профиль + список его тестов |
| GET | `/api/v1/admin/assessments/{id}` | полный результат одного теста (JSON) |
| GET | `/api/v1/admin/assessments/{id}/export` | тот же результат теста в CSV |

## 2. Список юзеров

```text
GET /api/v1/admin/users?page=1&limit=20&search=ivan&age_group=senior&status=completed&goal=university
```

- `page`/`limit` — как везде в админке (1-based, лимит 1..100, по умолчанию 20).
- `search` — по `User.email`, регистронезависимо, частичное совпадение.
- `age_group` — новый фильтр, опционален: `junior`/`middle`/`senior`. Фильтрует
  по `Profile.age_group` юзера напрямую.
- `status` — новый фильтр, опционален: `in_progress`/`completed`.
- `goal` — новый фильтр, опционален: `explore`/`profession`/`university`/`unsure`.

**⚠️ Важная семантика `status`/`goal`: "у юзера есть ХОТЯ БЫ ОДИН тест,
подходящий под фильтр" — не обязательно его САМЫЙ ПОСЛЕДНИЙ тест.** Если
юзер проходил тест дважды — первый раз с `goal=explore`, затем ещё раз с
`goal=university` — он попадёт в выдачу и по `goal=explore`, и по
`goal=university`. При этом колонка `latest_assessment_status`/
`latest_assessment_goal` в ответе всегда показывает правда самый свежий тест,
независимо от того, по какому фильтру юзер нашёлся — не путайте эти два
понятия при рисовке UI (например, не подсвечивайте карточку юзера как
"последний тест — university", если он нашёлся по фильтру `goal=university`,
но на деле у него более свежий тест с другой целью).

Сортировка фиксирована — по `created_at` (новые сверху).

```jsonc
{
  "items": [
    {
      "id": "e78dd10f-0527-4bd8-bb83-b4a9bc724287",
      "email": "user@example.com",
      "is_verified": true,
      "is_active": true,
      "is_admin": false,
      "created_at": "2026-08-28T09:20:13Z",
      "has_profile": true,
      "profile_name": "Arman",
      "age_group": "senior",              // новое поле; null если анкета не заполнена
      "assessments_count": 2,
      "latest_assessment_status": "completed",
      "latest_assessment_goal": "university",  // новое поле; null если тестов ещё нет
      // riasec/big_five — админ-only СЫРЫЕ проценты по ПОСЛЕДНЕМУ ЗАВЕРШЁННОМУ
      // тесту (не обязательно latest — если самый свежий тест ещё in_progress,
      // берётся последний перед ним completed). Ключи фиксированы:
      "riasec": {"R": 60.8, "I": 62.6, "A": 62.3, "S": 57.4, "E": 57.5, "C": 63.8},
      // null для junior (там инструмент MI, не RIASEC — намеренно не путается
      // в одну форму) и для юзеров без завершённого теста вообще.
      "big_five": {"N": 51.0, "E": 52.1, "O": 47.9, "A": 56.2, "C": 42.7}
    }
  ],
  "total": 252,
  "page": 1,
  "limit": 20
}
```

## 3. Экспорт списка в CSV

```text
GET /api/v1/admin/users/export?search=...&age_group=...&status=...&goal=...
Authorization: Bearer <token>
```

Те же фильтры, что и §2, **без** `page`/`limit` — выгружает ВСЕХ юзеров,
подходящих под фильтр, за один запрос. Ответ — не JSON, а файл:
`Content-Type: text/csv`, `Content-Disposition: attachment;
filename=users_export.csv`. На фронте — обычная ссылка/кнопка `<a href=... download>`
либо `fetch` + `blob` + программный клик, тело ответа руками не парсить как JSON.

Колонки (фиксированный порядок, всегда все присутствуют, пустая строка вместо
`null`):

```
id,email,is_verified,is_active,is_admin,created_at,has_profile,profile_name,
age_group,assessments_count,latest_assessment_status,latest_assessment_goal,
riasec_R,riasec_I,riasec_A,riasec_S,riasec_E,riasec_C,
big_five_N,big_five_E,big_five_O,big_five_A,big_five_C
```

`riasec_*`/`big_five_*` — пустые для junior/без результата, как и в JSON-версии.
**Без пагинации на большой базе это может быть тяжёлым запросом** — если юзеров
станет много тысяч, разумно предупреждать админа в UI ("выгрузка может занять
время") или сначала сузить фильтром, прежде чем нажимать экспорт.

## 4. Детали юзера

```text
GET /api/v1/admin/users/{user_id}
```

404 → `{"detail": "User not found"}`.

```jsonc
{
  "id": "...", "email": "...", "is_verified": true, "is_active": true, "is_admin": false,
  "created_at": "...",
  "profile": { /* ProfileResponse — см. docs/frontend-result-api-contract.md, или null если анкета не заполнена */ },
  "artifacts": [ /* ArtifactItem[] — загруженные сертификаты/файлы */ ],
  "assessments": [
    {
      "id": "52469def-ef55-49c2-8b64-b958525d604c",
      "goal": "university",
      "status": "completed",
      "answered_count": 314,
      "total_questions": 314,
      "created_at": "...",
      "completed_at": "...",
      "has_result": true,     // есть ли AnalysisResult — если true, GET .../assessments/{id} вернёт analysis_result
      "has_roadmap": true     // есть ли Roadmap
    }
  ]
}
```

`assessments` отсортирован по `created_at` (новые сверху) — это список всех
тестов юзера, не только последнего. Клик по строке → §5 по `id` этого теста.

## 5. Детали одного теста (полный результат)

```text
GET /api/v1/admin/assessments/{assessment_id}
```

404 → `{"detail": "Assessment not found"}`.

```jsonc
{
  "id": "...", "user_id": "...", "user_email": "...", "profile_name": "Arman",
  "goal": "university", "status": "completed",
  "answered_count": 314, "total_questions": 314,
  "created_at": "...", "completed_at": "...",
  "responses": [
    {
      "question_id": "...", "instrument": "riasec",   // "riasec" | "big_five" | "mi"
      "category": "R",     // riasec_type / bigfive_domain / mi_category letter-or-key, в зависимости от instrument
      "question_text": "Мне нравится решать практические, приземлённые задачи",
      "question_order": 1,
      "answer_value": 5, "selected_answer_text": "Точно про меня",
      "created_at": "..."
    }
    // ... один объект на каждый отвеченный Likert-вопрос, отсортировано по question_order
  ],
  "motivation_responses": [
    {
      "triplet_index": 0,
      // Каждый триплет — 3 показанных юзеру утверждения (разных категорий
      // мотивации), из которых он выбрал одно как САМОЕ важное и одно как
      // НАИМЕНЕЕ важное. picked_most_*/picked_least_* — это РЕАЛЬНЫЙ ответ
      // юзера (клик), не статичный контент триплета. not_picked_* — третье
      // утверждение, которое юзер не трогал ни в ту, ни в другую сторону
      // (вычисляется как "осталось", отдельно нигде не хранится).
      "picked_most_text": "...", "picked_most_category": "interest",
      "picked_least_text": "...", "picked_least_category": "money",
      "not_picked_text": "...", "not_picked_category": "stability",
      "created_at": "..."
    }
    // senior's MOST/LEAST-триплеты; пусто для junior/middle (у них своя
    // motivation-pairs форма, здесь пока не эндпоинчена отдельно)
  ],
  "analysis_result": {
    // AdminAnalysisResultResponse — null пока тест не завершён/не посчитан.
    // Полный сырой результат: profile (riasec ИЛИ mi-ключи, см. ниже),
    // code, meta (differentiation/consistency/aversion), careers[],
    // strengths[], weaknesses[], development_plan, big_five, thinking_style,
    // personality_profile/notes/highlights, motivation/motivation_top/
    // motivation_highlights, strength_cards[], thinking_style_notes[],
    // report_version, summary. Раскладку и происхождение полей см. §5.1.
    "id": "...", "assessment_id": "...",
    "profile": {"R": 60.8, "I": 62.6, "A": 62.3, "S": 57.4, "E": 57.5, "C": 63.8},
    "code": ["C", "A", "I"],
    "meta": {"differentiation": 0.34, "consistency": "high", "aversion": {"S": 2}},
    "careers": [
      {"slug": "...", "name": "...", "holland_code": "CAI", "match_score": 87,
       "description": "...", "professions": [...], "skills_needed": [...],
       "subjects_to_develop": [...], "first_steps": [...]}
    ],
    "strengths": ["C", "A"], "weaknesses": ["S"],
    "development_plan": {"reinforce": [...], "compensate": [...]},
    "big_five": {"N": 51.0, "E": 52.1, "O": 47.9, "A": 56.2, "C": 42.7},
    "thinking_style": {"creative_think": 62.0, "systematic": 71.0, "strategic": 55.0, "practical": 68.0},
    "personality_highlights": ["..."], "personality_profile": {...}, "personality_notes": {...},
    "motivation": {"interest": 6, "creation": 5, "...": 0},
    "motivation_top": ["interest", "creation"], "motivation_highlights": ["..."],
    "strength_cards": [], "thinking_style_notes": [],   // v2-поля, пусто пока не сгенерированы
    "report_version": 1, "summary": "...", "created_at": "..."
  },
  "roadmap": { /* RoadmapResponse — см. docs/frontend-roadmap-api-contract.md, или null */ }
}
```

### 5.1 `analysis_result.profile` — RIASEC или MI, зависит от возраста

**Ключи `profile`/`code` — НЕ всегда RIASEC-буквы.** Для junior (инструмент —
MI, не Holland-коды) это ключи вида `verbal`/`logical`/`musical`/`visual`/
`bodily`/`interpersonal`/`intrapersonal`/`naturalistic`. Для middle/senior —
привычные `R`/`I`/`A`/`S`/`E`/`C`. Определяйте, что показывать, по
`profile.age_group` соответствующего юзера (§4), не по форме самого объекта.
Ровно поэтому в списковом эндпоинте (§2) `riasec` — отдельное, фиксированной
формы поле, которое бэкенд сам оставляет `null` для junior, а не переиспользует
`profile` напрямую.

## 6. Экспорт одного теста в CSV (внутри ZIP)

```text
GET /api/v1/admin/assessments/{assessment_id}/export
Authorization: Bearer <token>
```

404 → `{"detail": "Assessment not found"}` (обычный JSON, не файл, если тест
не найден). При успехе — файл, `Content-Type: application/zip`,
`Content-Disposition: attachment; filename=assessment_<id>.zip`.

**Это ZIP, не голый CSV** — внутри 2 или 3 отдельных `.csv`-файла, у каждого
своя ровная (не "рваная") структура: один заголовок, одинаковое число колонок
во всех строках. Раньше это были 3 блока разной ширины подряд в одном CSV —
такое нормально открывается в Excel/Numbers (там можно промотать), но
ломается в любом инструменте, который ожидает одну единую таблицу (веб
csv-превьюеры, `pandas.read_csv` и т.п. — первая строка задаёт число колонок,
всё, что шире, обрезается/съезжает). На фронте — просто отдаём файл как есть
(`blob` + `download`, `Content-Type: application/zip`), **не** пытаться
распарсить это как CSV/JSON напрямую.

**`summary.csv`** — 2 колонки, `Metric,Value` (метаданные + весь
`analysis_result` построчно):
```
Metric,Value
user_email,user@example.com
profile_name,Arman
goal,university
status,completed
created_at,2026-08-28T09:20:13+00:00
completed_at,2026-08-30T10:00:00+00:00
answered_count,314
total_questions,314
has_roadmap,True
report_version,1
summary,...
code,C, A, I
profile_R,60.8
profile_I,62.6
...                          # по одной строке на каждый ключ profile/big_five/
                              # meta.aversion/thinking_style/personality_profile/
                              # personality_notes/motivation — динамически,
                              # ключи зависят от возраста (см. §5.1)
meta_differentiation,0.34
meta_consistency,high
strengths,C, A
weaknesses,S
development_plan_reinforce,...
development_plan_compensate,...
personality_highlights,...
motivation_top,interest, creation
motivation_highlights,...
careers_count,8
careers_top,Аналитик (87), Дизайнер (82), ...   # топ-5 карьер "имя (score)", не весь список
```
Если `analysis_result` ещё `null` (тест не завершён/не посчитан) — этот
"хвост" отсутствует, файл обрывается на `has_roadmap`. Не баг, ожидаемое
поведение для незавершённых тестов.

**`responses.csv`** — таблица ответов, 7 колонок:
```
question_order,instrument,category,question_text,answer_value,selected_answer_text,created_at
1,riasec,R,"Мне нравится решать практические, приземлённые задачи",5,"Точно про меня",2026-08-29T16:32:24.131065+00:00
...
```
`created_at` — время конкретного ответа (когда юзер ответил именно на этот
вопрос, не время создания теста в целом). Присутствует в архиве всегда (даже
пустой — только с заголовком, если `answered_count=0`).

**`motivation.csv`** — таблица мотивационных триплетов, **7 колонок, но
файла в архиве вообще не будет**, если `motivation_responses` пуст (junior/
middle — у них своей мотивационной формы здесь нет, не путать с пустым
файлом-с-заголовком, как у `responses.csv`):
```
triplet_index,picked_most_text,picked_most_category,picked_least_text,picked_least_category,not_picked_text,not_picked_category
0,"Решать сложные задачи, за которые не все берутся",challenge,"Заниматься тем, что мне по-настоящему интересно",interest,Приносить пользу людям и помогать им,helping
```

**Это реальные ответы юзера, не статичный контент триплетов.** В каждом
триплете юзеру показывались 3 утверждения (разных категорий мотивации), и он
выбирал одно как самое важное для себя, другое — как наименее важное:
`picked_most_*` — что выбрано как САМОЕ важное (реальный клик),
`picked_least_*` — что выбрано как НАИМЕНЕЕ важное (реальный клик),
`not_picked_*` — третье утверждение из триплета, которое юзер вообще не
трогал ни в одну сторону (это не отдельный ответ, а "то, что осталось" —
явно нигде не хранится, вычисляется на лету).

## 7. Ошибки

Идентично остальным admin-контрактам: 401/403 по токену (§1 университетского
контракта). 404-тексты:

| Эндпоинт | 404 detail |
|---|---|
| `GET /users/{id}` | `{"detail": "User not found"}` |
| `GET /assessments/{id}`, `GET /assessments/{id}/export` | `{"detail": "Assessment not found"}` |

`GET /users`, `GET /users/export` не 404-ят — пустой список/пустой CSV
(только заголовок), если ничего не подошло под фильтр.

## 8. Что нужно построить на фронте

1. **Таблица юзеров** — колонки из §2 (email, профиль, возраст, статус/цель
   последнего теста, riasec/big_five как компактные бейджи или мини-график),
   фильтры `age_group`/`status`/`goal` как селекты рядом с поиском по email,
   пагинация. Помните разницу "нашёлся по фильтру" vs. "его последний тест"
   (§2, предупреждение) — не путайте их визуально.
2. **Кнопка "Экспорт CSV"** на этой же странице, дергает §3 с текущими
   применёнными фильтрами (так пользователь может сначала сузить список, а
   потом выгрузить именно то, что видит).
3. **Страница юзера** — профиль + таблица его тестов (§4.assessments) с
   бейджами `has_result`/`has_roadmap`, клик по тесту → страница результата.
4. **Страница результата теста** — рендерит §5 целиком: сырые
   riasec/big_five/motivation числа, careers как карточки, thinking_style,
   personality_profile/notes, плюс таблица всех сырых ответов (`responses`)
   для тех, кто хочет провалиться в детали. Кнопка "Скачать (ZIP)" рядом,
   дергает §6.
5. Общий момент: `profile`/`code` внутри `analysis_result` — MI-ключи для
   junior, RIASEC-буквы для middle/senior (§5.1) — не хардкодьте набор из 6
   RIASEC-букв при рендере этого конкретного поля, только для отдельного
   `riasec`-поля в списковом эндпоинте (§2) это безопасно.
