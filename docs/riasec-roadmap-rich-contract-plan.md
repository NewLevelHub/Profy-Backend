# План: догнать roadmap до богатого контракта поверх RIASEC/MI

Дата: 2026-08-05. Автор: обсуждение с владельцем продукта + 2 сессии Backend
Architect (аудит текущего кода + проектирование), проверено прямым чтением
кода (не пересказ агентов) непосредственно перед фиксацией этого документа.

Статус: **план зафиксирован, реализация не начата.** Это справочный документ
для следующей сессии реализации — в нём написано, что и где менять, но код
ещё не тронут.

---

## 0. Что этот документ заменяет

Старые доки (`docs/frontend-roadmap-api-contract.md`,
`docs/roadmap-content-generation.md`, `docs/roadmap-goal-contract.md`,
`docs/riasec-roadmap-tasks.md`, `docs/riasec-results-tasks.md`,
`docs/roadmap-known-goal-notes.md`) описывают roadmap-пайплайн **на старом
движке вопросов** (24-осевой belief-walk, `AssessmentSession.belief`) и
предполагали, что переход на RIASEC ещё не решён (задача #15 там висела
🔴 заблокированной).

С тех пор в коде произошёл **полный хард-каттовер со старого движка**
(`alembic/versions/0024_riasec_migration.py`) — старый движок физически
удалён (`TRUNCATE` + `DROP COLUMN`, без дискриминатора вида
`is_riasec`/`is_akinator`, вопреки рекомендованному в доках прецеденту
AKN-021). После merge `origin/New-Test-Logic` целевой interest instrument
зависит от возраста: **junior — MI, middle/senior — RIASEC**. Вместе с
движком **переписали и сам roadmap**, но не в том виде, который описывают
старые доки — получилась более простая версия. Этот документ фиксирует:
(1) как выглядит реально задеплоенная архитектура сегодня, (2) что решено
делать дальше, (3) что именно и где менять.

Старые доки не удаляются (историческая ценность/контекст решений), но
**не считать их источником истины по текущему контракту** — используйте этот
файл.

---

## 1. Архитектура сегодня (проверено прямым чтением кода)

Ключевая находка, которую не увидели ни доки, ни первый черновой пересказ
в этом чате: сейчас **две независимые системы роадмапа**, а не одна.

### 1.1 Goal roadmap — `RoadmapResponse` (таблица `roadmaps`)

- Эндпоинты: `POST /roadmap/generate` (body: `assessment_id`,
  `program_id?`) → `GET /roadmap/{assessment_id}` (`app/routers/roadmap.py:46-53,83-93`).
  Один роадмап на `assessment_id` (`Roadmap.assessment_id` — `unique=True`,
  `app/models/roadmap.py:17-22`).
- 5 горизонтов: `HORIZONS = ["month_1", "months_3", "months_6", "year_1", "until_goal"]`
  (`app/services/roadmap_builder.py:52`).
- Генерация: LLM-first (`_build_roadmap_ai`, `app/prompts/roadmap.py`) с
  детерминированным фолбэком по цели (`_build_explore`/`_build_profession`/
  `_build_university`, `roadmap_builder.py:92-273`) — единственное место,
  где вообще есть fallback без LLM во всём модуле.
- Источник направлений для middle/senior: `AnalysisResult.careers` (уже
  отранжирован по match_score), top-3 через `_DirectionSummary`
  (`roadmap_builder.py:56-87`). У junior `careers=[]`: goal roadmap не
  должен выдумывать профессии по MI, а использует MI activities и остальные
  безопасные сигналы контекста.
- **Только здесь** работает `goal=university`: гэп-анализ по
  `Program.requirements/deadlines/grants` (`app/services/gap_analysis_service.py`)
  превращается в текст задач `month_1`/`months_3` (`_build_university`,
  `roadmap_builder.py:200-233`) — **не** в отдельные структурированные поля
  ответа.

### 1.2 Direction roadmap — `DirectionRoadmapResponse` (таблица `direction_roadmaps`)

- Эндпоинты: `POST /roadmap/direction` (body: `assessment_id`,
  **один** `direction_slug`, не список) → `GET /roadmap/{assessment_id}/directions/{slug}`
  (`roadmap.py:56-80`). Много роадмапов на assessment — по одному на
  подтверждённое направление (`UniqueConstraint(assessment_id, direction_slug)`,
  `app/models/direction_roadmap.py:19-21`).
- 4 горизонта, **другие имена**, чем в старых доках:
  `DIRECTION_HORIZONS = ["months_3", "months_6", "months_9", "months_12"]`
  (`app/schemas/roadmap.py:6`) — нет `month_1` и нет `until_admission`.
- AI-only, **без фолбэка** — при сбое LLM 503 (`_AI_UNAVAILABLE`,
  `roadmap_builder.py:429-432`).
- Гейт доступа (`_require_direction_roadmap_access`, `roadmap_builder.py:476-515`):
  не junior, **`goal != university`** (университет полностью исключён из
  этой ветки — ошибка прямо говорит "используется план по программе
  университета", т.е. отправляет в 1.1), и обязательно пройденный
  AI-опрос по направлению (`DirectionInquiry` должен существовать для этого
  `slug` — `direction_inquiry_service.get_inquiry`).
- **Генерация автоматически подтверждает направление**: `assessment.
  selected_direction_slug = slug` выставляется безусловно внутри
  `generate_direction_roadmap` (`roadmap_builder.py:588`) — это прямое
  расхождение со старым goal-контрактом (`docs/roadmap-goal-contract.md` §1.2:
  "generating a plan under explore/unsure... must not silently confirm it").
  Сейчас подтверждение и генерация — одно действие, без отдельного шага.
- Поля ответа: `target` (`role`/`why`/`horizon_years`), `growth_focus`
  (`weakness`/`why_it_matters`/`evidence`, 3-источниковая цепочка),
  `stages[]` (`horizon`/`title`/`outcome`/`steps[]`/`integration_project`,
  каждый `step` — `text`/`description`/`track` (profile|growth|integration)/
  `category`/`priority`), `skills_to_build` (плоский список строк),
  `subjects_to_focus` (плоский список строк, **без** заметки/веса),
  `university_track` (`specialties[]`/`prepare[]` — плоские списки, **не**
  структурированные дедлайны/гранты/язык/портфолио из старых доков).
- **Нет полей**: `profession_options[]`, `subjects_now[].note`,
  `starter_actions`, ни в одной из двух систем.

### 1.3 `Direction` — плоский каталог профессий, не иерархия

`scripts/riasec_professions.py` — ~150 отдельных профессий с 3-буквенным
Holland-кодом каждая (`"Air Traffic Controller"`, `"Actuary"`, ...).
`scripts/seed_riasec_directions.py:35-46,63-83` пишет в БД **только**
`name`/`slug`/`holland_code` — четыре описательных поля модели
(`description`/`professions`/`skills_needed`/`subjects_to_develop`/
`first_steps`, все на `app/models/direction.py:28-32`, все
`nullable=False, default="" / list`) сегодня **пустые у каждой из ~150
строк**, подтверждено чтением сид-скрипта, не предположение.

Важное следствие: **одна строка `Direction` = одна профессия**, не
"направление с несколькими профессиями внутри", как было в старом каталоге
сфера→лист. Это меняет, куда физически может лечь `profession_options[]`
(см. Область 3 ниже) — старая идея "3-5 профессий внутри направления" не
транспортируется 1-в-1.

### 1.4 `StudentContext` — единый age-aware источник сигнала

`app/services/student_context.py` читает общий storage
`AnalysisResult.profile/code/strengths/weaknesses`, но семантика этих полей
зависит от возраста: junior хранит MI keys, middle/senior — RIASEC keys.
Дополнительно контекст содержит `Profile.subjects_*`, `Artifact` и
опциональный `DirectionInquiry` через `inquiry_slug`.

Goal roadmap обязан учитывать discriminator/возраст: для junior использовать
MI interests/activities и не строить career claims. Direction roadmap
недоступен junior, поэтому его interest evidence остаётся RIASEC. Нельзя
называть общий `StudentContext` «полностью RIASEC» или передавать junior
MI keys в промпт под инструкцией «Holland code».

---

## 2. Принятые решения (из обсуждения 2026-08-05)

1. **Направление движения**: догонять roadmap до богатого контракта из
   старых доков, а не фиксировать текущий простой контракт как окончательный.
2. **`growth_focus`**: добавить 4-й источник — кросс-направленческий
   `DirectionInquiry` с низким `readiness` по другим slug'ам того же
   assessment'а.
3. **`subjects_now`/заметки по предмету**: 2-уровневая цепочка
   (самоотчёт `Profile.subjects_hard/easy/liked/disliked` → нейтральная
   заметка). Без измеренного тира (нет RIASEC-нативной замены старому
   `subject_readiness`-квизу) и без `weight` (нет данных под него).
4. **Цель `known`**: выносится в полностью отдельный продуктовый разговор,
   вне текущего скоупа. `AssessmentGoal` сегодня — только
   `explore/profession/university/unsure` (`app/models/assessment.py:12-16`).

---

## 3. Детальный план по областям

### Область 1 — контент-бэкфилл `Direction`

**Текущее состояние**: `description`/`professions`/`skills_needed`/
`subjects_to_develop`/`first_steps` — пустые у всех ~150 строк (см. §1.3).

**Кого это блокирует**: Область 2 (`starter_actions` ← `first_steps`) и
Область 3 (`why` ← `description`/`skills_needed`) напрямую. Также усиливает
качество обеих систем сразу — `_DirectionSummary` в goal roadmap
(`roadmap_builder.py:56-87`) и `_direction_brief()` в direction roadmap
(`app/prompts/direction_roadmap.py:225-232`) оба читают эти же поля.

**Что менять**: не код — данные. Написать/сгенерировать контент для
~150 строк `Direction`: `description` (1-2 предложения), `skills_needed`
(3-6 тегов), `subjects_to_develop` (список школьных предметов),
`first_steps` (2-3 действия по правилам платформенного whitelist'а —
см. Область 2). Формат уже есть в модели, просто нужно наполнение — либо
ручная курация, либо разовый LLM-проход с ручной проверкой.

**Не заблокировано ничем**, можно начинать сразу.

---

### Область 2 — `starter_actions`

**Текущее состояние**: `direction.first_steps` существует и уже долетает
до `_direction_brief()` (`direction_roadmap.py:225-232`) — то есть модель
*видит* его в промпте направления — но никак не возвращается клиенту:
`DirectionRoadmapResponse` не имеет поля `starter_actions`, и `_generate_plan`
его не запрашивает.

**Важное уточнение по сравнению с прошлым обсуждением**: `DIRECTION_HORIZONS`
начинается с `months_3` (§1.2) — в direction roadmap **нет** горизонта
`month_1`. Значит `starter_actions` — это не дублирование `months_3`, а
реальный незакрытый разрыв: ничего в текущем контракте не покрывает
"что сделать прямо сейчас/на этой неделе" для уже подтверждённого
направления. Это снимает риск задвоения с `months_3`, о котором говорилось
на этапе обсуждения — этап `months_3` начинается только через 3 месяца,
`starter_actions` закрывает промежуток до него.

**Что менять**:
- `app/schemas/roadmap.py`: добавить `starter_actions: list[str]` в
  `DirectionRoadmapResponse` (и в `_DirectionPlan`/`_upsert_direction_roadmap`
  в `roadmap_builder.py:436-444,597-630`).
- `app/models/direction_roadmap.py`: новая JSONB-колонка `starter_actions`
  + миграция alembic.
- `app/services/roadmap_builder.py`, `_generate_plan`/`_upsert_direction_roadmap`:
  логика "curated (`direction.first_steps`) если непусто, иначе LLM-фолбэк".
- `app/prompts/direction_roadmap.py`: добавить `starter_actions` в
  `DIRECTION_ROADMAP_SCHEMA` (обязательное поле при LLM-фолбэке) и раздел
  промпта с правилами: 2-3 действия, один ученик, платформенный whitelist
  (тот же принцип "не выдумывать бренды/курсы/кружки", что уже есть в
  промпте для `steps`, `direction_roadmap.py:199-204` — переиспользовать
  формулировку, не изобретать новую).

**Зависит от**: Области 1 (для честного curated-варианта; LLM-фолбэк можно
включить и раньше, но тогда `starter_actions` всегда будет LLM-сгенерирован,
даже когда контент для направления появится позже).

---

### Область 3 — `profession_options[].why` / `.practice`

**Существенная переоценка по сравнению с прошлым обсуждением.** Раньше
предполагалось, что это поле — часть direction roadmap (`DirectionRoadmapResponse`).
Но раз `Direction` = одна профессия (§1.3), к моменту генерации
direction roadmap профессия уже одна и уже подтверждена самим фактом
прохождения `DirectionInquiry` по этому slug'у — "3-5 вариантов профессий
внутри направления" там физически нечем наполнить.

Естественное место для этого поля — **goal roadmap** (`RoadmapResponse`,
Область 1.1), а конкретно шаблоны `_build_explore`/`_build_profession`
(`roadmap_builder.py:92-197`), которые уже берут top-3
`AnalysisResult.careers` (эти карьеры уже отранжированы по `match_score`
— `app/services/riasec_service.py`, вес 3/2/1 по топ-3 буквам кода
ученика). Это ближе по смыслу к старой идее `profession_options[]`, чем
что-либо в direction roadmap.

Поле применимо только к RIASEC-ветке middle/senior. Для junior
`AnalysisResult.careers=[]`; вместо `profession_options` UI/goal roadmap
использует MI `exploration_activities` и не делает ранних карьерных выводов.

**Что менять** (требует отдельного продуктового решения о форме ответа,
не просто код):
- Либо добавить `profession_options: list[ProfessionOption]` как новое
  поле `RoadmapResponse` (goal roadmap) параллельно с `milestones`, либо
  завести отдельный лёгкий эндпоинт "варианты профессий по результатам"
  поверх `AnalysisResult.careers` + LLM-слой `why`.
- `why` пишется LLM только когда есть реально различающий сигнал между
  top-N карьерами в конкретном ответе (переносится правило честности из
  старых доков как есть) — контент для этого берётся из
  `Direction.description`/`skills_needed` (Область 1) плюс
  `match_score`/`holland_code` каждой карьеры (уже есть в
  `ContextCareer`, `app/schemas/student_context.py:15-24`).
- `.practice` — новый `RoadmapTask`-подобный элемент на профессию,
  генерируется тем же способом, что и `starter_actions` (Область 2):
  LLM с платформенным whitelist'ом.

**Открытый вопрос перед реализацией** (не решён в этом документе): в какую
именно систему это идёт — расширение `RoadmapResponse.milestones`-ответа
новым полем, или отдельный "career options" эндпоинт. Нужно решить до
написания схемы, иначе рискуем переусложнить `RoadmapResponse`.

---

### Область 4 — `growth_focus`, 4-й источник (решено, добавляем)

**Текущее состояние**: 3 источника, зашиты прямо в текст промпта, не в код
(`app/prompts/direction_roadmap.py:112-117`):
1. `inquiry.low_signals` (утверждения, с которыми ученик не согласился);
2. `weaknesses` (RIASEC-типы с низким баллом);
3. `subjects_hard`/`subjects_disliked`, только если предмет релевантен
   направлению.

**Целевое состояние**: 4-й источник — `DirectionInquiry` по **другим**
`direction_slug`, которые ученик проходил в рамках того же
`assessment_id`, с низким `readiness`. Сигнал "попробовал другое
направление, получил низкий вердикт, и там было что-то релевантное
текущему" — валидная эвиденция для точки роста (продуктовое решение
принято, см. §2.2).

**Что менять**:
- `app/services/student_context.py`, `build_student_context`: добавить
  запрос всех `DirectionInquiry` для `assessment_id`, исключая текущий
  `inquiry_slug` (новый запрос рядом с существующим на
  `student_context.py:112-121`).
- `app/schemas/student_context.py`: новое поле на `StudentContext`, например
  `other_inquiries: list[ContextInquiry] = []` (переиспользовать
  существующую модель `ContextInquiry`, `student_context.py:27-37`).
- `app/prompts/direction_roadmap.py`: добавить 4-й пункт в список
  "допустимые источники" (`_SYSTEM_PROMPT`, строки 112-117) с явным
  указанием — использовать только если `readiness` низкий и найденное
  релевантно текущему направлению; учесть, что `readiness` — свободная
  русская строка (`"Высокая готовность"|"Средняя готовность"|"Стоит
  присмотреться"`, `direction_inquiry_service.py:141-145` пишет её из ответа
  LLM без валидации по enum) — сравнение делать по подстроке/маппингу,
  не по строгому equality, и заранее закладывать, что формулировка может
  измениться, если промпт `direction_inquiry.py` поменяется.

**Риск**: если ученик пока не проходил AI-опрос ни по одному другому
направлению — источник просто пуст, цепочка падает на источники 1-3 как
сегодня. Это ожидаемое поведение, не баг.

---

### Область 5 — `subjects_now[].note` (решено: 2 уровня, без weight)

**Текущее состояние**: `subjects_to_focus` — плоский `list[str]` на
`DirectionRoadmapResponse` (`app/schemas/roadmap.py:103`), без заметки,
LLM сам решает содержимое без структурированной цепочки приоритета.

**Целевое состояние**: `subjects_now: list[SubjectNote]` с полем `note`
на каждый предмет, цепочка 2 уровня:
1. Самоотчёт — `Profile.subjects_easy/hard/liked/disliked` (уже есть в
   `StudentContext`, `student_context.py:131-134`) — если предмет из
   `direction.subjects_to_develop` встречается в одном из этих списков,
   персонализируем заметку под него.
2. Нейтральная заметка ("этот предмет входит в программу направления")
   — если сигнала по предмету нет вообще.

**Явно не делаем**: измеренный тир (нет замены старому
`subject_readiness`-квизу — решение принято, не заводим новый инструмент
измерения сейчас) и `weight` (нет данных, нет источника для калибровки
числа).

**Что менять**:
- `app/schemas/roadmap.py`: новая модель `SubjectNote(subject: str, note: str)`,
  заменить `subjects_to_focus: list[str]` на `subjects_now: list[SubjectNote]`
  на `DirectionRoadmapResponse` (breaking change контракта — фронтенду
  нужно будет перейти на новую форму, план не предполагает
  сосуществования двух форм этого поля).
- `app/prompts/direction_roadmap.py`: `DIRECTION_ROADMAP_SCHEMA` —
  заменить `subjects_to_focus` на `subjects_now` с объектной формой;
  добавить в `_SYSTEM_PROMPT` 2-уровневое правило (аналогично `growth_focus`
  по стилю изложения — "заметка обязана опираться на реальный сигнал или
  быть честно нейтральной, не выдумывать уровень").
- `app/services/roadmap_builder.py`: `_DirectionPlan`/`_upsert_direction_roadmap`
  — переименовать поле, обновить сериализацию.

**Не заблокировано** ничем из Областей 1-4, можно делать параллельно.

---

### Область 6 — цель `known` (вынесена отдельно, вне скоупа)

Старый flow (`GET /directions/tree`, `KnownProfessionQuiz`,
`known_profession_service`, `KnownProfessionQuizLog`) удалён вместе со
старым движком — держался на иерархии сфера→лист, которой в RIASEC-каталоге
больше нет (§1.3: сейчас плоский список профессий). Это не "доделать", а
**спроектировать заново** под плоский каталог: как выглядит "уже знаю
профессию" пикер без дерева, нужен ли вообще отдельный валидационный квиз
или можно переиспользовать `DirectionInquiry`, как это соотносится с новым
`AssessmentGoal` enum. Требует отдельного продуктового разговора, не
раньше, чем Области 1-5 стабилизируются.

---

### Область 7 — university richness (открыт 2026-08-05, **решён 2026-08-06 через Область 8**)

**Университетская ветка отдаёт заметно меньше структуры, чем старые доки.**
Старые доки (`docs/roadmap-goal-contract.md` §4) описывали
`university_requirements[]` — структурированный список по каждой
программе: `application_deadline`, `grants[]`, `language_level`,
`portfolio_needed`, `required_documents[]`, всё backend-populated из
`Program`, без LLM. До Области 8 для `goal=university` работал только
**goal roadmap** (§1.1, не direction roadmap — тот вообще исключал
university, §1.2), и университетская специфика проявлялась только как
**текст внутри milestone-задач**, сгенерированный из `GapAnalysisResult`
(`app/services/gap_analysis_service.py`: `met`/`not_met`/`in_progress`/
`unknown`/`readiness_score` по ключам из `Program.requirements`,
классифицированным эвристикой `_classify_key` в gpa/language/exam/portfolio).
`Program.deadlines`/`Program.grants` (JSONB, поля физически существуют,
`app/models/program.py:29-31`) в `RoadmapResponse` вообще не попадали ни в
каком виде — гэп-анализ их не читал.

ТЗ (§20.5, §34.6 — критерий приёмки) требует эту структуру явно, не как
рекомендацию — поэтому статус поднят с «можно отложить» до «решается в
рамках этой инициативы». Решение и конкретный план — см. Область 8 ниже:
university перестаёт быть отдельной, более бедной веткой и получает
структурированный `university_requirements[]` внутри той же
`DirectionRoadmapResponse`, что и остальные цели.

---

### Область 8 — унификация goal-веток direction roadmap + разбор возраста (решено 2026-08-06)

**Контекст обсуждения.** Вопрос был поставлен так: нужен ли отдельный
промпт на каждую цель (`explore`/`profession`/`university`) и отдельный
промпт на каждую возрастную группу? Ответ разный для двух осей — их нельзя
решать одинаково.

#### 8.1 Возраст — параметр внутри промпта, без изменений

Возраст меняет **глубину и словарь**, а не структуру ответа — это не повод
для отдельных файлов. Уже сегодня `direction_roadmap.py` делает это
правильно: секция `_SYSTEM_PROMPT` «ГЛУБИНА — СТРОГО ПО ВОЗРАСТУ»
(`direction_roadmap.py:186-192`) — один текст с тремя диапазонами
(10-13/14-15/16-17), `context.age`/`context.age_group` передаются моделью
как данные, не как выбор промпт-файла. Дробить это на 3 копии значило бы
дублировать все остальные правила промпта (честность `growth_focus`,
platform whitelist, структура этапов) три раза с гарантированным дрейфом
между копиями. **Решение: не трогать.**

#### 8.2 Цель — да, но ветвление внутри общего промпта/схемы, не 3 файла

ТЗ §23.3 прямо расписывает разное **содержание** по сценарию (A — пробы,
B — развитие навыков, C — подготовка к поступлению) — это реальное
основание для goal-branching, не просто идея. Но правильная форма —
не 3 независимых промпт-файла, а:

1. Общий блок правил (honesty у `growth_focus`, platform whitelist,
   структура stages, возрастная глубина из §8.1) остаётся один на всех —
   как сейчас.
2. Небольшая goal-specific секция инструкций внутри `_SYSTEM_PROMPT`,
   выбираемая по `context.goal`, — эмфаза содержания `stages.steps` по
   сценарию (пробы / практика и навыки / подготовка к поступлению, по
   формулировкам §23.3), а не отдельная схема ответа.
3. Один backend-populated блок (`university_requirements`), который
   заполняется **не моделью** и не входит в её JSON-schema вообще — как и
   `skills_to_build`/`university_track`, это не решение LLM.

**Главный практический вывод: не строить 4-й параллельный промпт для
university, а завести university в тот же direction-roadmap пайплайн,
которым уже пользуются `profession`/`explore`/`unsure`.** Сегодня это
единственная цель, у которой в принципе нет доступа к честному
`growth_focus`, к 4-горизонтной структуре этапов, ко всему, что несёт
direction roadmap — не потому что так решили, а потому что её туда не
пустили изначально (`_require_direction_roadmap_access`, ниже).

#### 8.3 Конкретные изменения

**Доступ.** `app/services/roadmap_builder.py`, `_require_direction_roadmap_access`
(строки ~498-502) — убрать блок
`if assessment.goal == AssessmentGoal.university: raise HTTPException(...)`
(текст ошибки "Для цели «поступление» используется план по программе
университета" уходит вместе с ним). Остальной гейт не меняется: не junior,
обязателен пройденный `DirectionInquiry` по этому `slug` — university
проходит тот же путь подтверждения направления, что и остальные цели, это
не исключение, а согласованность.

**Новые схемы** (`app/schemas/roadmap.py`), по прецеденту уже
спроектированному в `docs/roadmap-goal-contract.md` §4 (та же дисциплина
null-значит-нет-данных, что и там):

```python
class ProgramGrant(BaseModel):
    name: str
    amount: str | None = None
    conditions: str | None = None

class UniversityRequirement(BaseModel):
    program_name: str
    university_name: str
    city: str
    exams: list[str]
    application_deadline: str | None = None
    grants: list[ProgramGrant] = []
    language_level: str | None = None
    portfolio_needed: bool | None = None
    required_documents: list[str] | None = None
```

`DirectionRoadmapResponse` — добавить `university_requirements:
list[UniversityRequirement] = []`. `DirectionRoadmap` (модель, JSONB) —
новая колонка `university_requirements`, миграция alembic.

**Наполнение — только backend, только для `goal == university`.**
`app/services/roadmap_builder.py` — новая функция
`_university_requirements_for(slug: str, db) -> list[UniversityRequirement]`:
запрос `Program` по `Program.direction_slug == slug` (поле уже есть,
`app/models/program.py:23`) с join на `University` (`name`/`city`,
`app/models/university.py:15-17`), маппинг `Program.requirements`/
`deadlines`/`grants` в те же три поля с той же null-дисциплиной, что уже
описана в `docs/roadmap-goal-contract.md` §4 (`min_ielts`→`language_level`,
`needs_portfolio`→`portfolio_needed` как есть включая `false`,
`needs_essay`/`needs_recommendations`→`required_documents`). Вызывается
**только когда `context.goal == "university"`** — для остальных целей
список остаётся `[]`. Это не техническое ограничение, а прямое следствие
принципа ТЗ «не строить роадмап в обход цели»: ребёнку, который выбрал
«разобраться в себе», незачем видеть дедлайны и портфолио вуза.

**Промпт** (`app/prompts/direction_roadmap.py`):
- Добавить `_GOAL_FOCUS: dict[str, str]` — короткий абзац на
  `explore`/`unsure` (эмфаза на пробах, формулировки уже частично намечены
  в `roadmap-content-generation.md` про секцию «ПОНЯТЬ СЕБЯ»),
  `profession` (эмфаза на практике/навыках), `university` (эмфаза на
  соответствии `stages` реальным срокам — если `university_requirements`
  непусто, шаги `months_9`/`months_12` могут честно ссылаться на
  конкретный дедлайн/экзамен из данных, не выдумывая его).
- `build_messages` — вставляет `_GOAL_FOCUS.get(context.goal, "")` в
  промпт и прокидывает уже посчитанный `university_requirements` в
  context-payload, если он есть, — ровно тот же принцип «реальные факты
  отдельно от LLM-слоя», что уже используется для `Direction.professions`/
  `skills_needed` (`_direction_brief`).
- Схема `DIRECTION_ROADMAP_SCHEMA` **не меняется по цели** — у модели
  всегда один и тот же JSON-контракт, ветвится только текст инструкций.
  `university_requirements` в схему ответа модели не входит вообще (как
  `skills_to_build` не решение модели о структуре, только о содержании).

**Что не трогаем.** Goal roadmap (`app/services/roadmap_builder.py`,
`_build_university`/`generate_roadmap`, §1.1) остаётся как есть — это
первичный обзорный слой, доступный сразу после теста, ещё без
подтверждённого направления и без `DirectionInquiry`. Direction roadmap
становится опциональным глубоким слоем поверх него для всех 4 целей
одинаково, university в этом смысле догоняет остальные три, а не заменяет
собой goal roadmap. Осознанное решение, не недосмотр — ломать то, что уже
работает как первый экран результата, нет причины.

**Зависимости.** Не блокирует и не блокируется Областями 1-6. Разрешает
Область 7 полностью. Пересекается с Областью 3 (`profession_options`)
только текстуально — goal-specific абзац для `profession` в `_GOAL_FOCUS`
касается содержания `stages.steps`, а не решает вопрос про список
профессий-кандидатов, эти два вопроса независимы.

---

### Область 9 — глубина текста + Big Five/мотивация в промптах (решено 2026-08-07)

**Контекст обсуждения.** Жалоба «план в одно предложение» относится **конкретно
к goal roadmap** (`app/prompts/roadmap.py`), не к обоим роадмапам —
проверено: `ROADMAP_JSON_SCHEMA` требует от задачи только `text`/`category`/
`priority`, поля `description` в JSON-схеме для модели нет вообще, хотя оно
есть на самой Pydantic-модели `RoadmapTask.description`. Direction roadmap
(`direction_roadmap.py`) уже просит 3-5 предложений на шаг — там другая
проблема (глубина есть, но зажата механическим лимитом и не использует
Big Five/мотивацию).

Отдельно решено: использовать данные Big Five и мотивации, которые уже
считаются в `AnalysisResult`, но никогда не попадают в `StudentContext`
(проверено — ни `student_context.py`, ни оба промпта роадмапа их не читают).
Источник raw motivation зависит от возраста: junior/middle — Harter pairs,
senior — triplets. После `report_service.build_report` это не две формы
контракта: оба пути дают единые `motivation_top`/`motivation_highlights`.

#### 9.1 Что добавляем в `StudentContext` — только безопасный, уже готовый текстовый слой

**Критично**: `AnalysisResult.big_five` и `AnalysisResult.motivation`
(сырые баллы) помечены в модели как **admin-only** (`app/models/
analysis_result.py:30,33` — прямая ссылка на ТЗ §18.3: сырые проценты
ребёнку не показываются). Кормить ими промпт напрямую — риск, что модель
процитирует число в тексте, который увидит ребёнок. К счастью, для отчёта
уже посчитан безопасный производный слой (`bigfive_content.py`,
`report_service.py:176`) — именно его и берём:

| Добавить в `StudentContext` | Источник (`AnalysisResult`) | Почему безопасно |
|---|---|---|
| `personality_profile: dict[str, float] = {}` | `personality_profile` | Display-ready 5 черт (N уже развёрнут в `emotional_stability`, высокое значение = всегда позитивно) |
| `personality_notes: dict[str, str] = {}` | `personality_notes` | Готовая RU-фраза с честной градацией high/low/mid на черту (`bigfive_content._NOTES`) |
| `thinking_style: dict[str, float] = {}` | `thinking_style` | Тот же производный слой, что уже в отчёте (§18.2 п.4) |
| `motivation_top: list[str] = []` | `motivation_top` | Категориальный список, не число |
| `motivation_highlights: list[str] = []` | `motivation_highlights` | Готовые RU-фразы «что тебя драйвит» |

**Не добавляем** `big_five`/`motivation` (сырые) в `StudentContext` вообще —
нет причины отходить от правила «admin-only» ради промпта, безопасный
эквивалент уже есть.

`StudentContext` и prompts не должны знать, из какой таблицы пришла
мотивация. Но completion/retake logic до построения контекста обязана
ветвиться: `motivation_pair_responses` для junior/middle и
`motivation_responses` для senior.

`app/services/student_context.py`, `build_student_context` — добавить пять
строк по образцу уже существующих (`profile=dict(analysis.profile) if
analysis else {}` и т.д.).

**Побочный эффект бесплатно**: `roadmap_prompt.build_messages` (goal
roadmap) уже делает `context.model_dump_json(indent=2)` целиком — расширение
`StudentContext` автоматически долетает и туда, без отдельной проводки.
Инструкции по использованию (ниже) всё равно нужно дописать в оба промпта
отдельно.

#### 9.2 Куда вплетать — не размазывать по всем полям

Три точки, не «в каждый шаг»:

1. **`target.why`** (direction roadmap) — точка синтеза всех трёх
   результатов: почему роль подходит по интересу (RIASEC, как сейчас) **и**
   по стилю работы (1-2 реально релевантные черты из `personality_notes`,
   не все 5 механически) **и** по тому, что мотивирует (`motivation_top`).
   Модель выбирает, что из этого реально относится к делу — тот же принцип,
   что уже работает в `growth_focus` (один источник из нескольких, не смесь
   всех).
2. **`growth_focus`** — новый, 5-й источник (после 4-го из Области 4):
   `personality_notes` с тиром `low`, **только если черта релевантна
   требованиям конкретного направления** (низкая `conscientiousness` —
   реальный риск для направления с длинными самостоятельными проектами;
   низкая `extraversion` не имеет отношения к «инженерии», но имеет — к
   «журналистике»). Без явной привязки к требованию направления источник не
   используется — иначе это тот же необоснованный психоанализ, от которого
   и так защищает вся эта цепочка.
3. **1-2 шага в `stages`, где это про способ действия, а не про
   содержание** — например, «как начать проект» может честно опираться на
   `personality_notes` («тебе комфортнее с проверенными способами — начни с
   готового шаблона»), а «изучи основы Python» — нет, там личность ни при
   чём.

#### 9.3 Замена лимита предложений на качественный критерий

**Direction roadmap** (`direction_roadmap.py`, раздел «ОПИСАНИЕ ШАГА»):
убрать формулировку «3-5 предложений», заменить на явный критерий работы
предложения — каждое обязано либо (а) сказать, что конкретно делать, либо
(б) объяснить связь именно с этим учеником со ссылкой на конкретный сигнал,
либо (в) дать проверяемый критерий готовности. Явный запрет на
generic-фразы без указания, что именно и почему у ЭТОГО ученика.

**Goal roadmap** (`app/prompts/roadmap.py`): добавить `description` в
`ROADMAP_JSON_SCHEMA` (`_STEP_SCHEMA`-подобно — сейчас поля там нет вообще,
см. контекст выше) как обязательное поле, с тем же качественным критерием,
но короче — задачи goal roadmap по природе более ранние/общие, чем этапы
direction roadmap, не нужно требовать той же плотности.

Без замены критерия «уберём лимит» даст более длинный, но не более живой
текст — при отсутствии чёткого критерия «что считается работой»,
освободившееся место модель по умолчанию заполняет общими фразами.

#### 9.4 Честность источников — расширить на новые поля

Правило `growth_focus`, «допустимые источники — ТОЛЬКО эти N, иначе не
выдумывай», явно распространяется на `target.why` и на новый 5-й источник:
модель обязана указать, какая конкретно черта/мотив и почему релевантны
именно этой роли/направлению — не «упомяни что-нибудь из
personality_notes».

**Смежная находка, тем же охватом, что и здесь.** Текущая инструкция
`growth_focus` уже просит: «...или назови тип из weaknesses **с его баллом
из profile**». Это инструкция цитировать сырой процент в поле `evidence`,
которое, по докстрингу `GrowthFocus.evidence`, **показывается ребёнку в
UI** (`app/schemas/roadmap.py`, класс `GrowthFocus`: «shown in the UI so
the student can see why we said it»). Это тот же риск, что мы только что
закрыли для personality/motivation (§9.1), только для RIASEC он уже в
проде. Предлагаю поправить формулировку заодно: цитировать **тип
(«Investigative»/буква из code)**, не процент — тип уже не число, этого
достаточно для «честного основания», без нарушения §18.3. Не отдельная
задача, а однострочная правка того же промпт-раздела, который и так
трогаем в §9.2/9.4.

**Зависимости.** Не блокирует и не блокируется остальными областями.
Пересекается с Областью 4 (5-й источник `growth_focus` идёт после уже
запланированного 4-го, не вместо него) и с Областью 3 (`target.why` и
`profession_options.why` — разные поля разных систем, синтез Big
Five/мотивации в `target.why` не отменяет и не подменяет честность-правило
`profession_options.why`, если/когда та область будет реализована).

---

## 4. Что не входит в скоуп (явно)

- Join-таблица `Direction.holland_code` → профессия с confidence/
  provenance (задача #20 из старых доков) — не блокирует ни одну из
  областей 1-5 (см. §1.3, matching работает на плоской колонке уже сейчас).
  Отдельный бэклог-айтем, если понадобится точность матчинга.
- Feature-flag на откат старого 24-осевого движка — он уже недвусмысленно
  и необратимо заменён (данные физически удалены миграцией 0024), отката
  на уровне кода не существует. Текущий age split MI/RIASEC — часть нового
  движка, а не coexistence со старым.

---

## 5. Сводная таблица

| Область | Что меняется | Где | Статус |
|---|---|---|---|
| 1. Контент-бэкфилл `Direction` | Данные, не код | `directions` (БД) | Решено, не начато |
| 2. `starter_actions` | Схема + модель + миграция + промпт | `roadmap.py` (schema/model), `roadmap_builder.py`, `direction_roadmap.py` (prompt) | Решено, ждёт область 1 |
| 3. `profession_options[].why/.practice` | Новое поле/эндпоинт, форма не решена | `RoadmapResponse` (goal roadmap), возможно новый роутер | **Открыт вопрос формы**, ждёт область 1 |
| 4. `growth_focus` 4-й источник | Новый запрос + поле контекста + промпт | `student_context.py`, `schemas/student_context.py`, `direction_roadmap.py` (prompt) | Решено, не начато |
| 5. `subjects_now[].note` | Breaking change поля, схема + промпт | `schemas/roadmap.py`, `roadmap_builder.py`, `direction_roadmap.py` (prompt) | Решено, не начато |
| 6. Цель `known` | Новая подсистема с нуля | Всё новое | Вынесено отдельно |
| 7. University richness | Решено через Область 8 | — | Решено, см. Область 8 |
| 8. Goal-ветвление + university в direction roadmap | Убрать гейт, новые схемы `UniversityRequirement`/`ProgramGrant`, `_university_requirements_for`, `_GOAL_FOCUS` в промпте | `roadmap_builder.py`, `schemas/roadmap.py`, `models/direction_roadmap.py` (+миграция), `direction_roadmap.py` (prompt) | Решено, не начато |
| 9. Глубина текста + Big Five/мотивация в промптах | 5 новых полей `StudentContext`, `description` в goal roadmap schema, качественный критерий вместо лимита предложений, 5-й источник `growth_focus`, правка цитирования балла в `evidence` | `schemas/student_context.py`, `services/student_context.py`, `prompts/roadmap.py`, `prompts/direction_roadmap.py`, `schemas/roadmap.py` | Решено, не начато |
