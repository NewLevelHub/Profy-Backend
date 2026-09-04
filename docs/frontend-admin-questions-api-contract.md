# Admin Question-Bank Content Editing API — контракт для фронтенда

**Статус: реализовано на ветке `pro-226`, актуально на 2026-09-02.**
Основано на прямом чтении `app/routers/admin.py`, `app/schemas/admin_content.py`,
`app/services/admin_content_service.py`, `app/services/admin_lock.py` и
`docs/admin-questions-content-overrides-plan.md`.

Фронтенд — отдельный репозиторий (Profy-Frontend), этот документ — контракт
для его команды: что вызывать и как отрисовывать/сабмитить в админке для
контента вопросников — RIASEC/Big Five/MI-вопросов, форс-чойс пар,
мотивационных утверждений/пар и справочника направлений (профессий).

Это сиблинг-документ к `docs/frontend-admin-university-api-contract.md` —
доступ (JWT + `is_admin`) и общая механика partial-PATCH там устроены
одинаково; здесь описано только то, что отличается, плюс полный список
эндпоинтов/полей для этой части.

## 1. Доступ

Идентично университетам/программам — `Authorization: Bearer <jwt>`,
`get_current_admin_user` на каждый запрос. См. §1
`frontend-admin-university-api-contract.md`, не дублирую здесь.

## 2. Эндпоинты (обзор)

| Method | Path | Назначение |
|---|---|---|
| GET | `/api/v1/admin/questions` | список + фильтры |
| GET | `/api/v1/admin/questions/{id}` | детали одного вопроса |
| PATCH | `/api/v1/admin/questions/{id}` | редактирование вопроса |
| GET | `/api/v1/admin/question-pairs` | список + фильтры |
| GET | `/api/v1/admin/question-pairs/{id}` | детали одной пары |
| PATCH | `/api/v1/admin/question-pairs/{id}` | редактирование пары |
| GET | `/api/v1/admin/motivation-statements` | список |
| GET | `/api/v1/admin/motivation-statements/{id}` | детали одного утверждения |
| PATCH | `/api/v1/admin/motivation-statements/{id}` | редактирование утверждения |
| GET | `/api/v1/admin/motivation-pairs` | список |
| GET | `/api/v1/admin/motivation-pairs/{id}` | детали одной пары |
| PATCH | `/api/v1/admin/motivation-pairs/{id}` | редактирование пары |
| GET | `/api/v1/admin/directions` | список + поиск |
| GET | `/api/v1/admin/directions/{id}` | детали одного направления |
| PATCH | `/api/v1/admin/directions/{id}` | редактирование направления |

Создания/удаления через API нет ни для одной из этих 5 сущностей — см. §8.

## 3. Ключевое отличие от университетов: `overrides` вместо `admin_locked_fields`

У University/Program лок — это **список имён полей** (`admin_locked_fields:
string[]`), само значение живёт только в живой колонке. Здесь — **словарь
"имя поля → значение"** (`overrides: dict`), потому что контент вопросников
не просто перезаписывается редеплоем, а может целиком **удаляться** (seed-
скрипт чистит строки, которых больше нет в bank-файле), и `overrides`
одновременно и защищает поле, и хранит само отредактированное значение —
самодостаточно, без похода в живую колонку.

Практические следствия для фронта:

- Списковые эндпоинты (`AdminQuestionListItem` и т.д.) отдают **не** сам
  словарь, а `has_overrides: boolean` — есть ли вообще хоть один override у
  строки. Показывайте это как бейдж/значок в таблице ("отредактировано
  админом"), полный список изменённых полей — только на странице деталей.
- Детальные эндпоинты (`AdminQuestionDetail` и т.д.) отдают полный
  `overrides: dict`, например `{"text": "Новая формулировка"}`. UI логика та
  же, что и с `admin_locked_fields` (§7 университетского контракта): значок
  замочка на конкретном инпуте, если его ключ есть в `overrides`.
- **Снять override с поля через API нельзя** — как и `admin_locked_fields`,
  это односторонний механизм (см. §8).
- Строка, у которой есть хотя бы один override, **не может быть удалена**
  редеплойным seed-скриптом, даже если её ключ (`order`/`pair_index`/`slug`/
  ...) больше не встречается в bank-файле — то есть залоченная-хоть-чем-то
  строка переживёт даже переупорядочивание контент-банка на бэкенде.

## 4. Partial-PATCH — та же механика и то же самое предупреждение

Как и с университетами (см. §5 п.1-2 того контракта):

1. Поле трогается, только если ключ присутствует в теле PATCH
   (`exclude_unset=True`). Явный `null` — это осознанная очистка поля, не то
   же самое, что не прислать ключ.
2. **⚠️ Каждый присланный ключ попадает в `overrides` — независимо от того,
   изменилось ли реально значение.** Те же правила: **PATCH только dirty-
   полями формы, никогда не всей формой целиком.** Здесь цена ошибки выше,
   чем у университетов — залоченное поле у вопроса не просто "перестанет
   обновляться", а строка ещё и не будет удаляться при реорганизации
   контент-банка, даже если это давно не нужно.

Ответ каждого PATCH — обновлённый `*Detail` целиком (со свежим `overrides`).

## 5. Questions (RIASEC / Big Five / MI — общая таблица)

```text
GET /api/v1/admin/questions?page=1&limit=20&instrument=riasec&age_tier=senior&search=приземлённые
```

- `instrument` — опционален, один из `riasec` / `big_five` / `mi`. Без
  фильтра список смешивает все три инструмента — сортировка сначала по
  `instrument`, потом по `order`, так что на экране без фильтра инструменты
  идут блоками, не вперемешку.
- `age_tier` — опционален, `junior` / `middle` / `senior`. **Это НЕ "только
  для этого возраста"** — `Question.age_tier` работает как порог видимости
  (`app/services/age_tiers.py:visible_tiers`, `junior ⊆ middle ⊆ senior`), но
  сам фильтр здесь — точное совпадение `age_tier == значение`, не диапазон.
  Присылая `age_tier=junior`, вы увидите только вопросы, у которых видимость
  начинается именно с junior, а не все вопросы, видимые junior-пользователю.
- `search` — ищет по `Question.text`, регистронезависимо, частичное
  совпадение.

```jsonc
// AdminQuestionListItem
{
  "id": "20fa4752-6ccf-4e8b-996b-d4df7bf4ca65",
  "instrument": "riasec",
  "text": "Мне нравится решать практические, приземлённые задачи",
  "order": 1,
  "age_tier": "senior",
  "riasec_type": "R",           // null если instrument != riasec
  "bigfive_domain": null,       // null если instrument != big_five
  "mi_category": null,          // null если instrument != mi
  "has_overrides": false
}
```

```jsonc
// GET /api/v1/admin/questions/{id} -> AdminQuestionDetail
{
  "id": "...",
  "instrument": "riasec",
  "riasec_type": "R",
  "bigfive_domain": null,
  "mi_category": null,
  "facet": null,                 // используется только для big_five
  "keyed": null,                 // "plus"/"minus", только для big_five
  "text": "...",
  "short_text": null,            // форма для junior forced-choice UI, может быть null
  "icon": null,
  "order": 1,
  "age_tier": "senior",
  "overrides": {}
}
```

Редактируемые поля (`AdminQuestionUpdateRequest`, все опциональны):
`riasec_type`, `bigfive_domain`, `mi_category`, `facet`, `keyed`, `text`,
`age_tier`, `short_text`, `icon`. `instrument` и `order` — **read-only**, не
входят в схему (смена `instrument`/`order` — структурная операция, не
"правка контента", вне скоупа этого API).

**⚠️ Не показывайте одной формой все возможные поля сразу** — реальный
осмысленный набор зависит от `instrument`: для `riasec`-строки имеет смысл
редактировать `riasec_type`, для `big_five` — `bigfive_domain`+`facet`+
`keyed`, для `mi` — `mi_category`. Присылать в PATCH поле не своего
инструмента технически не запрещено (бэкенд не валидирует консистентность),
но это создаст мусорные данные — постройте форму так, чтобы показывать
только релевантные для `instrument` этой строки поля.

## 6. Question pairs (форс-чойс)

```text
GET /api/v1/admin/question-pairs?page=1&limit=20&instrument=riasec&age_tier=junior
```

Те же семантики `instrument`/`age_tier`, что и в §5, но здесь `age_tier` у
пары — **не** префиксная видимость, а точная принадлежность одной возрастной
группе (см. докстринг `QuestionPair` в `app/models/question_pair.py`) — пара
целиком принадлежит junior **или** middle, не обеим сразу.

```jsonc
// AdminQuestionPairListItem
{
  "id": "...", "instrument": "riasec", "age_tier": "junior",
  "pair_index": 3, "has_overrides": false
}
```

```jsonc
// GET .../question-pairs/{id} -> AdminQuestionPairDetail
{
  "id": "...", "instrument": "riasec", "age_tier": "junior", "pair_index": 3,
  "question_a_id": "...", "question_b_id": "...",   // read-only, см. ниже
  "frame": "Что бы ты выбрал?",       // null у junior — просто пара иконок без сценария
  "option_a_text": "Починить велосипед",  // null = использовать question.short_text/text
  "option_b_text": null,
  "option_a_icon": "🔧",
  "option_b_icon": null,
  "overrides": {}
}
```

Редактируемые поля (`AdminQuestionPairUpdateRequest`, все опциональны):
`frame`, `option_a_text`, `option_b_text`, `option_a_icon`, `option_b_icon`.

**`question_a_id`/`question_b_id`/`age_tier`/`pair_index`/`instrument` —
read-only**, не входят в схему. Это осознанное решение: смена того, какие
`Question`-строки образуют пару — структурная правка, не контентная, и в
неё сознательно не пускают через этот API (см. Design в
`docs/admin-questions-content-overrides-plan.md`).

**Отображение опций в UI:** `option_a_text`/`option_a_icon` могут быть
`null` — в таком случае реальный текст/иконка на экране пользователя
берутся из связанного `Question.short_text`/`.text`/`.icon` (см.
`app/services/question_pair_service.py`). Если админ хочет посмотреть, что
реально увидит пользователь для стороны с `null`-переопределением, форме
нужно отдельно подтянуть `GET /admin/questions/{question_a_id}` — этот
эндпоинт сам не резолвит fallback.

## 7. Motivation statements (MOST/LEAST триплеты, senior)

```text
GET /api/v1/admin/motivation-statements?page=1&limit=20
```

Без фильтров по `search`/категории — только пагинация, сортировка по
`triplet_index`, потом `order`.

```jsonc
// AdminMotivationStatementListItem
{
  "id": "...", "triplet_index": 0, "order": 0,
  "category": "interest", "text": "...", "has_overrides": false
}
```

```jsonc
// GET .../motivation-statements/{id} -> AdminMotivationStatementDetail
{
  "id": "...", "triplet_index": 0, "order": 0, "category": "interest",
  "text": "Взрослый вариант формулировки",
  "text_junior": null,   // junior-версия той же карточки, null = используется text для всех
  "overrides": {}
}
```

Редактируемые поля: `category`, `text`, `text_junior`.

**Групповая логика триплетов не проверяется бэкендом:** 3 строки с одним
`triplet_index` должны покрывать 3 разные категории (проверяется генератором
в `scripts/motivation_statement_bank.py`, не в БД/API) — PATCH одной строки
на категорию, уже занятую в этом же триплете, технически пройдёт и создаст
дубль категории внутри триплета. Если это важно для UX, добавьте клиентскую
проверку (запросить остальные 2 строки триплета перед сохранением).

## 8. Motivation pairs (Harter-style, junior/middle)

```text
GET /api/v1/admin/motivation-pairs?page=1&limit=20
```

Пагинация, сортировка по `pair_index`.

```jsonc
// AdminMotivationPairListItem
{
  "id": "...", "pair_index": 0,
  "category_a": "interest", "category_b": "interest", "has_overrides": false
}
```

```jsonc
// GET .../motivation-pairs/{id} -> AdminMotivationPairDetail
{
  "id": "...", "pair_index": 0,
  "category_a": "interest", "category_b": "interest",
  "text_a": "Одни ребята готовы часами заниматься любимым делом...",
  "text_b": "...",
  "overrides": {}
}
```

Редактируемые поля: `category_a`, `category_b`, `text_a`, `text_b`.

**`category_a` == `category_b` всегда** (это НЕ сравнение двух разных
категорий — обе стороны одна и та же категория, `text_a` её позитивный
полюс, `text_b` — негативный, см. докстринг `MotivationPair`). Форма должна
это отражать — например, один селектор категории на пару, а не два
независимых.

## 9. Directions (справочник профессий/направлений)

```text
GET /api/v1/admin/directions?page=1&limit=20&search=психолог
```

`search` — по `Direction.name`, регистронезависимо, частичное совпадение.
Сортировка — по имени (A→Z).

```jsonc
// AdminDirectionListItem
{
  "id": "...", "name": "Психолог", "slug": "psiholog",
  "holland_code": "SIA", "has_overrides": false
}
```

```jsonc
// GET .../directions/{id} -> AdminDirectionDetail
{
  "id": "...", "name": "Психолог", "slug": "psiholog", "holland_code": "SIA",
  "description": "",              // пусто по умолчанию для большинства строк, см. ниже
  "professions": [],
  "skills_needed": [],
  "subjects_to_develop": [],
  "first_steps": [],
  "overrides": {}
}
```

Редактируемые поля (`AdminDirectionUpdateRequest`, все опциональны):
`name`, `holland_code`, `description`, `professions` (`list`),
`skills_needed` (`list`), `subjects_to_develop` (`list`), `first_steps`
(`list`).

**Важное отличие от остальных 4 сущностей: у `description`/`professions`/
`skills_needed`/`subjects_to_develop`/`first_steps` вообще нет риска
затирания редеплоем** — seed-скрипт (`scripts/seed_riasec_directions.py`)
трогает только `name` и `holland_code`, эти пять полей не пишет никогда (см.
докстринг `Direction` в `app/models/direction.py`). Редактируйте их как
обычные PATCH-поля без опасений — override всё равно проставится (это
безобидно, просто не несёт практического смысла для этих полей), но никакой
логики "защиты от отката" тут реально не задействовано.

**`slug` — read-only**, не в схеме. Генерируется bank-скриптом
транслитерацией из `name` при первой заливке и после этого не меняется даже
если `name` отредактировать через это PATCH — расхождение имя/slug возможно
и ожидаемо, не баг.

`professions`/`skills_needed`/`subjects_to_develop`/`first_steps` — **у
большинства строк пустые списки по умолчанию** (см. докстринг модели — новый
каталог профессий из `scripts/riasec_professions.py` пока заполняет только
`name`+`holland_code`). Не удивляйтесь пустой форме — это ожидаемое
состояние большей части каталога, а не баг API.

## 10. Ошибки

Идентично §8 университетского контракта: 401/403 по токену, 422 —
стандартная pydantic-валидация. 404-тексты по сущностям:

| Сущность | 404 detail |
|---|---|
| Question | `{"detail": "Question not found"}` |
| QuestionPair | `{"detail": "Question pair not found"}` |
| MotivationStatement | `{"detail": "Motivation statement not found"}` |
| MotivationPair | `{"detail": "Motivation pair not found"}` |
| Direction | `{"detail": "Direction not found"}` |

## 11. Что нужно построить на фронте

1. **5 отдельных списковых страниц/вкладок** — Questions, Question Pairs,
   Motivation Statements, Motivation Pairs, Directions. Общий паттерн:
   таблица + пагинация (`total`/`page`/`limit`, `Math.ceil` на фронте как и
   у университетов) + бейдж "отредактировано" по `has_overrides`.
2. **Questions** — фильтр по `instrument` (таб/селект) обязателен в UI,
   иначе список из 314 строк трёх разных инструментов вперемешку
   нечитаем. Форма редактирования должна показывать только поля, релевантные
   `instrument` этой строки (§5).
3. **Question Pairs** — при показе `option_a_text`/`option_b_text` со
   значением `null` подсвечивать в форме, что реально отрисуется fallback из
   связанного вопроса (§6), а не пустая строка — иначе админ решит, что поле
   пустое и его нужно заполнить, хотя на проде там уже что-то показывается.
4. **Motivation Pairs** — один общий контрол категории на пару, не два
   независимых (§8).
5. **Directions** — держите в уме, что для большинства строк
   `professions`/`skills_needed`/`subjects_to_develop`/`first_steps` пустые
   изначально (§9) — форма не должна выглядеть "сломанной" на пустых
   массивах, это нормальное состояние каталога.
6. **Общий `overrides`-индикатор**: как и с `admin_locked_fields`, значок
   замочка на конкретном инпуте, если его ключ есть в `overrides` детального
   ответа. Тот же общий `buildPatchBody(dirtyFields)`-хелпер, что
   рекомендован в §9 п.4 университетского контракта, стоит переиспользовать
   и здесь — правило "только dirty-поля" (§4) одинаково критично везде.

## 12. Что не реализовано

- **Нет создания/удаления** ни для одной из 5 сущностей — только чтение и
  PATCH существующих строк (структурные правки — какие вопросы образуют
  пару, какие профессии есть в каталоге — по-прежнему делаются только через
  правку bank-файлов на бэкенде и редеплой).
- **Нет эндпоинта снятия override** — как и `admin_locked_fields` у
  университетов, `overrides` можно снять сейчас только прямым вмешательством
  в БД.
- **Нет серверной валидации кросс-строчной консистентности** — ни для
  триплетов мотивации (§7), ни для `category_a == category_b` у
  motivation-пар (§8, хотя это и гарантировано генератором бэкенда для
  bank-контента, PATCH может это нарушить). Вся такая логика — на фронте,
  если она вообще нужна в UI.
