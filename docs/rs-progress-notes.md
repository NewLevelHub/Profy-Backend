# RS-тикеты по редизайну /result — заметки о прогрессе

Статус на 2026-08-11, ветка `pro-169`. Пишется как памятка на случай
потери контекста разговора — не проектная документация, обновлять по
мере продвижения или удалить, когда все RS-тикеты закрыты.

## Откуда контекст

Родительская задача — редизайн student `/result` под `TZ_Profi.md` §16–18.
Источники истины (лежат в родительской папке `ProOf/`, НЕ в этом репо):

- `../frontend-result-api-contract.md` — целевой student-контракт v2
  (`report_version`, `interest_instrument: mi|riasec`, `strength_cards`,
  без чисел/баллов для ребёнка).
- `../result-report-redesign-plan.md` — план реализации, писался
  относительно чекаута коллеги (`yessimkhanuly13`) — некоторые пути и номер
  миграции (`0040`) там расходятся с этой веткой, см. ниже.

Методика подтверждена отдельно (`../Большая документация.md`): junior = MI +
Big Five + Harter-пары мотивации; middle = RIASEC + Big Five (+ карточки-пары)
+ Harter; senior = RIASEC + Big Five + тройки MOST/LEAST.

## Расхождение веток — РЕШЕНО (2026-08-11, merge commit `c5c3817`)

`origin/new_roadmap` смёржена в `pro-169`. Миграция `0040` (university
requirements) подтянута, `alembic heads` — снова один head. Конфликт был не
только в номере миграции: на `new_roadmap` независимо появилась **своя**
pytest-инфраструктура (`tests/conftest.py` на реальной dev-БД с откатом
транзакции через `join_transaction_mode="create_savepoint"`, `pyproject.toml`,
6 файлов тестов по roadmap/university) и свой вариант той же
retake-инвалидации, что делалась в этой сессии раньше (см. п.1 ниже).

Решение (по выбору пользователя): их `conftest.py` — основа (реальная dev-БД,
не отдельная `profi_db_test`), 5 файлов тестов этой сессии адаптированы под
неё. Их `assessment_shared.invalidate_goal_roadmap(assessment_id: UUID, ...)`
сигнатура (бере bare id, не `Assessment`) выиграла — так было в их уже
смёрженном `test_goal_roadmap_retake_invalidation.py`, который иначе сломался
бы. `roadmap_builder._cache_key` — их вариант без хеширования (просто
`roadmap:{assessment_id}:{program_id|"none"}`), тоже проще.

**Важно для будущих тестов на этой ветке:** dev-БД в докере — общая,
НЕ пересоздаётся под каждый прогон, и в ней реальные seed-данные (~300
questions, ~90 directions, 18 motivation_pairs, 36 motivation_statements на
момент мержа). `db_session`-фикстура откатывает транзакцию после каждого
теста, но **глобальные счётчики** (`likert_total_questions`,
`motivation_service.total_triplets`, `motivation_pair_service.total_pairs`)
считают ВСЕ строки в таблице, не только добавленные тестом. Поэтому:
- для точечных сущностей (Direction.slug и т.п.) — используй `test-`
  префикс в идентификаторах и большой `limit`, где применимо;
- для логики, завязанной на глобальные totals (completion gate и т.п.) —
  monkeypatch сами функции подсчёта, а не пытайся насеять контролируемое
  количество строк в общую таблицу.

## Что сделано в этой сессии (не про сам /result контент)

Ключевой факт: **содержимое и формат student-ответа `/result` не менялось
вообще** — `app/schemas/result.py` (нулевой diff за всю сессию). Всё ниже —
интеграционная гигиена и подготовка почвы, не сам редизайн:

1. **Retake-инвалидация** (`app/services/assessment_shared.py`) — все 4
   entrypoint'а retake (`assessment_service`, `motivation_service`,
   `question_pair_service`, `motivation_pair_service`) сведены к общему
   `invalidate_retake()`; добавлен `invalidate_goal_roadmap()`, которого не
   было вообще. Формат кэш-ключа роадмапа сменён на
   `roadmap:{assessment_id}:{hash}` (был просто хэш) — чтобы можно было
   SCAN'ить и чистить все варианты по assessment_id.
2. **pytest-инфраструктура с нуля** — `tests/conftest.py`, `pytest.ini`.
   Раньше в бэкенде тестов не было вообще (ни `tests/`, ни pytest в
   requirements). Отдельная тестовая БД (`<db>_test`), транзакция на тест с
   откатом, автосброс всех Redis-синглтонов (`assessment_shared`,
   `report_service`, `roadmap_builder`, `direction_inquiry_service`,
   `app.routers.auth` — нашёл 5-й, которого не было в тикете).
   Попутно починил `app/models/__init__.py` — 5 моделей туда не
   импортировались (`Question`, `QuestionPair`, `Roadmap`, `Motivation*`),
   значит и Alembic autogenerate их не видел.
3. **`riasec_service.matched_careers`** — детерминированный tie-break по
   `slug` при равных `match_score` (было: порядок из БД, не гарантирован).
4. **Completion gate для `/result/generate`** (`report_service.py`) —
   раньше можно было сгенерировать отчёт по недопройденному тесту.
   Добавлена `_assert_assessment_complete()` (свои counts на каждый
   возраст: junior — MI+BigFive Likert + Harter-пары; middle — то же + RIASEC
   вместо MI; senior — RIASEC+BigFive + тройки MOST/LEAST), 409 при
   неполноте. Плюс: простановка `status=completed` и вставка
   `AnalysisResult` теперь один `db.commit()` — раньше были два отдельных
   коммита, между ними можно было потерять согласованность.
5. **Admin/student схемы разведены** — новый `app/schemas/admin_result.py`
   (`AdminAnalysisResultResponse`, `AnalysisMeta` — переименован из
   `RiasecMeta`, т.к. поле общее для MI и RIASEC). `schemas/admin.py` и
   `admin_service.py` переключены на него. `schemas/result.py` не тронут —
   будущая чистка student-контракта админку не заденет.
6. **Миграция `0041`** (`alembic/versions/0041_add_report_version_and_narrative_fields.py`)
   — добавила в `analysis_results` три поля: `strength_cards JSONB`,
   `thinking_style_notes JSONB` (оба `NOT NULL DEFAULT '[]'`), `report_version
   INTEGER NOT NULL DEFAULT 1`. Upgrade/downgrade/upgrade прогнан на реальной
   схеме. `report_version` — реально хранимое поле, не read-time константа:
   старые/непопулированные строки явно `1`, а не выводятся из «strength_cards
   пуст → значит legacy». Добавлено и в `AdminAnalysisResultResponse` (со
   своими типизированными `AdminStrengthCard`/`AdminThinkingStyleNote`) —
   `schemas/result.py` по-прежнему не тронут, эти поля пока нигде не
   заполняются (ждут будущего LLM narrative pipeline).
7. **Safe evidence catalog** — новый `app/schemas/report_narrative_context.py`
   (`EvidenceItem`, `ReportNarrativeContext`) и
   `app/services/report_narrative_context.py`
   (`build_report_narrative_context`, `unknown_source_ids`). Чистая функция
   без обращения к БД — принимает уже посчитанные значения (strengths,
   personality_profile/notes, thinking_style, motivation_top/highlights,
   subjects, artifacts), а не сырой `AnalysisResult`. Каждый факт — MI-
   категория (junior) или RIASEC-категория (middle/senior, никогда оба
   сразу), high-tier черта характера (`bigfive_content.is_high_tier` —
   новый public-хелпер поверх старого `_STRONG`), топ-2 стиля мышления,
   мотивация, предметы, артефакты — с `source_id`/`source_type`/безопасным
   текстом без чисел. Специально НЕ принимает raw profile/big_five/
   motivation/match_score/meta.aversion как параметры — из сигнатуры
   физически нечего утечь. `unknown_source_ids()` — заготовка для будущего
   валидатора LLM-ответа. Это ещё не сама генерация (промпт/валидатор/
   fallback) — только каталог, которым они будут пользоваться.

Все тесты (65 шт., включая 6 файлов из new_roadmap) реально проверены на
регрессию там, где это осмысленно: временно откатывал фикс/фикстуру,
убеждался что тест падает именно так, как ожидалось, затем восстанавливал.
Не просто «зелёный, значит работает».

## Narrative LLM + validation pipeline — СДЕЛАНО (2026-08-12)

Реализован промпт и полный generation pipeline поверх `ReportNarrativeContext`
(каталог из предыдущей сессии, п.7 выше):

- `app/schemas/report_narrative.py` — `ReportNarrativeOutput` (summary,
  strength_cards, interests, thinking_style_notes, motivation_narrative,
  career_narrative). `NarrativeCard`/`MotivationNarrative` несут
  `evidence_ids` (нужны только для валидации, в БД не пишутся — персистится
  по-прежнему `{title, description}` через `AdminStrengthCard`/
  `AdminThinkingStyleNote`, см. п.6 выше). `InterestCard` — отдельная форма
  без evidence_ids: `category`/`tier(strong|steady)` проверяются напрямую
  против каталога, а не по цитированию.
- `app/prompts/report_narrative.py` — strict JSON-схема (additionalProperties
  false, cardinality НЕ в схеме — strict mode это запрещает, как и в
  `roadmap.py`, поэтому "ровно 8 MI / 6 RIASEC" задаётся текстом промпта и
  проверяется валидатором) + системный промпт с полным текстом Приложения C
  (В.1 запрещено / В.2 разрешено), возрастным стилем и запретом на career-
  лексику для junior.
- `app/services/report_narrative_validator.py` — `validate()`: banned
  vocabulary (Приложение C + отдельный список career-терминов для junior),
  no-new-numbers (цифры/`%` где угодно в тексте — отклоняется), unknown
  evidence_ids (`report_narrative_context.unknown_source_ids`), cardinality
  (interests == полный набор категорий инструмента; thinking_style_notes ==
  число реальных сигналов в каталоге, НЕ константа 2; strength_cards в
  `[min(5,available), min(7,available)]` — не выдумывает карточки сверх
  того, что есть в evidence), career_narrative (пусто для junior; ≤3 и
  обязательно с riasec evidence_ids для middle/senior), язык (кириллица
  по-текстово, не агрегированно — иначе одно нерусское поле тонет в
  остальных русских), длины (эвристические потолки на возраст, не точные
  числа из ТЗ — там их и нет, только относительное "в 2-3 раза меньше").
- `app/services/report_narrative_fallback.py` — детерминированный билдер:
  строит тот же `ReportNarrativeOutput` без LLM, напрямую из
  `context.evidence` + `MI_LABELS`/`RIASEC_LABELS`. По построению всегда
  проходит `validate()` — это проверено тестами, не просто предполагается.
- `app/services/report_narrative_service.py` —
  `generate_report_narrative()`: до 3 попыток (1 + 2 retry) LLM→validate,
  затем безусловный fallback. Никогда не бросает исключение. Логирование —
  только коды `ValidationIssue.code` и класс исключения
  (`type(exc).__name__`), никогда `issue.detail` (там могут быть реальные
  evidence_id/фраза) и никогда `str(exc)` (в `LLMError` иногда попадает
  сырой фрагмент ответа модели) — покрыто отдельными тестами на утечку.
- Тесты: `tests/unit/test_report_narrative_{prompt,validator,fallback,service}.py`
  — 46 тестов, все зелёные вместе с полным сьютом (113/113).

- `career_narrative` в каталоге ничего не знает о конкретных
  направлениях/профессиях (в `ReportNarrativeContext` нет source_type
  "career") — он валиден только как обоснование "почему стоит посмотреть в
  сторону RIASEC-категории", без имён профессий/вузов. Список профессий
  внутри направления по-прежнему берётся из БД (ТЗ §17.3, "правило факта") и
  подаётся отдельно, не через этот pipeline — см. следующий раздел, это и
  есть та самая "отдельная задача".

## `/result` теперь реально отдаёт v2-форму — СДЕЛАНО (2026-08-12)

К моменту начала этого тикета выяснилось, что между записью выше и этим
моментом кто-то (параллельная сессия/чекаут — коммиты появлялись на диске
прямо во время работы, включая правки в файлах, которые редактировались в
это же время) уже сам подключил `generate_report_narrative()` к
`build_report()`: `strength_cards`/`thinking_style_notes`/`report_version=2`
уже писались в БД. Но:
- `narrative.summary` (из нового pipeline) реально не использовался —
  `summary` всё ещё шёл по старому отдельному пути
  (`_build_summary`/`_build_junior_summary`/AI-вызов через уже отдельный,
  ныне удалённый `app/prompts/report_summary.py`) — то есть LLM дёргался
  дважды с двумя независимыми генерациями, и результат одной из них просто
  выбрасывался;
- возврат `/result` (`build_report`/`get_report`, роутер) был всё ещё
  `AnalysisResultResponse` — старая сырая форма с процентами/кодами/
  match_score, несмотря на то что `report_version=2` уже писался в БД.

Сделано (после согласования с пользователем — их pipeline для текста,
отдельный слой для того, что pipeline сознательно не трогает):

- `app/schemas/result_v2.py` — `ResultResponseV2`, ровно форма из
  `frontend-result-api-contract.md`: `report_version: Literal[2]`,
  `interest_instrument`, `summary`, `strength_cards`, `interest_map`
  (`code`/`sphere`/`level` low|medium|high — ВСЕ 6/8 сфер, не только
  вычисленные как "сильная сторона"), `thinking_style_notes`,
  `motivation_highlights`, `careers` (`slug`/`rank`/`tier`/`why`/
  `matched_strengths`/`try_now`/...), `exploration_activities`,
  `is_flat_profile`, `created_at`.
- `app/services/report_v2_assembler.py` — вторая половина сборки, которую
  `report_narrative_*` пайплайн намеренно не делает: `interest_map` (из
  реальных нормализованных баллов, не из evidence-каталога — там только
  вычисленные "сильные стороны"), `careers` (из реальных `Direction` —
  `slug`/`match_score`/`first_steps` и т.д. — `career_narrative` пайплайна
  тут не участвует вообще), `is_flat_profile` (порог 25 по TZ §16.6, пока
  захардкожен — TZ §16.4 хочет это admin-настраиваемым, не сделано),
  `exploration_activities` для junior (гарантированно непустые:
  fallback на "по одному занятию на MI-категорию", если evidence вообще
  пуст).
- `app/services/report_service.py` — переписан: один вызов
  `generate_report_narrative()` даёт summary+strength_cards+
  thinking_style_notes согласованно (больше не два независимых вызова);
  `report_v2_assembler.assemble_result_v2()` собирает финальный ответ;
  кэш переехал на `report:v2:{id}` (был `report:{id}` — версионирование
  ключа, чтобы старый закэшированный v1-JSON никогда не прочитался как
  v2); `_shape_response()` — реконструирует `ResultResponseV2` из уже
  сохранённой строки без повторной генерации (cache-miss/DB-only путь):
  `strength_cards`/`thinking_style_notes` читаются как есть, инструмент
  (`mi`/`riasec`) определяется по ключам `analysis.profile` (буквы
  Holland уникальны и не пересекаются с MI-ключами).
- `app/routers/result.py` — `response_model` на `ResultResponseV2`.
- Удалён мёртвый код: `_build_summary`/`_build_junior_summary`/
  `_generate_ai_summary`, файл `app/prompts/report_summary.py` целиком.
- Контентные таблицы расширены под пункты 1-3 исходного тикета:
  `riasec_content.RIASEC_STRENGTH_PHRASES`/`NEUTRAL_CAREER_WHY`,
  `mi_content.MI_STRENGTH_PHRASES`, новый `thinking_style_content.py`.
  `report_narrative_context._interest_evidence` теперь берёт текст из
  этих *_STRENGTH_PHRASES вместо голых *_LABELS — то есть эти фразы
  реально текут и в AI-путь (как контекст для LLM), и в их
  deterministic fallback, не только в мой слой.
- Тесты: `tests/unit/test_report_v2_assembler.py` (8/6 интересов,
  careers=[] для junior, flat-profile → ровно 3 worth_trying,
  детерминизм — один и тот же вход дважды даёт побайтово одинаковый
  результат, пороги interest_map), `tests/integration/
  test_result_v2_fallback.py` (полный прогон через `build_report` с явно
  выключенным LLM — 200 + валидная v2-форма для junior и senior, cache-hit
  и DB-only reshape пути дают одинаковый результат).
- Попутно нашёл и починил: два теста в `test_report_completion_gate.py`
  (написанные параллельной сессией с комментарием "LLM is disabled in
  this test env") на самом деле реально стучались в OpenAI — в этом
  окружении `LLM_ENABLED=true` с рабочим ключом. Добавил явный
  `monkeypatch.setattr(llm_client, "is_enabled", lambda: False)` — прогон
  всего сьюта упал с ~44с до ~7с и перестал тратить реальные токены.

Все новые тесты реально проверены на регрессию (temporarily-break-then-
restore), включая полный прогон 124/124 на чистой пересборке.

## Финальная схема + discriminated union — СДЕЛАНО (2026-08-12)

Задача была не построить форму заново (её уже собрал `report_v2_assembler.py`
в предыдущем тикете), а зафиксировать её на уровне Pydantic-схемы, а не
только «ассемблер написан правильно»:

- `app/schemas/result_v2.py` — `ResultResponseV2` был один плоский класс,
  стал discriminated union: `MiResultResponse` | `RiasecResultResponse` по
  `interest_instrument`. Невозможные комбинации теперь ловит сама схема, а
  не тесты ассемблера: `MiResultResponse.careers` — `Field(max_length=0)`
  (не просто «assembler всегда передаёт []», а физически нельзя создать
  экземпляр с непустым careers), `interest_map` — `Field(min_length=8,
  max_length=8)` у MI / `6/6` у RIASEC, `RiasecResultResponse` — свой
  `@model_validator`: flat profile обязан иметь ровно 3 careers, все
  `tier="worth_trying"`, иначе `ValidationError`. Все модели —
  `model_config = {"extra": "forbid"}`.
  - Новое поле `disclaimer` (`DISCLAIMER` константа) — фиксированный,
    server-authored текст рамки возможностей (TZ §17.5 п.7), не зависит от
    LLM/возраста. `summary` по-прежнему может нести ту же мысль своими
    словами (промпт/fallback narrative-пайплайна не менялись) — `disclaimer`
    не замена, а гарантия, что фраза есть всегда, даже если генерация текста
    собьётся.
  - `StudentCareer.try_now` был `str | None`, стал обязательным непустым
    (`Field(min_length=1)`) — как и `why`. Fallback-текст на случай, если у
    `Direction` в БД нет `first_steps`: `riasec_content.NEUTRAL_TRY_NOW`
    (тот же паттерн, что уже был у `NEUTRAL_CAREER_WHY`).
  - `ResultResponseV2` (голый `Union`) — для type hints/`isinstance()`
    (работает в Python 3.10+ и с `typing.Union`, не только с `X | Y`).
    `ResultV2Schema` (`Annotated[..., Field(discriminator=...)]`) — то, что
    реально уходит в `response_model` роутера и в `TypeAdapter`
    (`ResultV2Adapter`, используется для чтения из Redis-кэша вместо
    `model_validate(json.loads(...))` — `TypeAdapter` умеет сам выбрать
    правильную ветку по `interest_instrument`, а один плоский класс не умел
    бы отличить, какую ветку валидировать).
- `app/services/report_v2_assembler.py`/`report_service.py` — оба места
  сборки ответа (`assemble_result_v2()` для свежей генерации,
  `_shape_response()` для DB-only reshape) теперь явно строят
  `MiResultResponse(...)`/`RiasecResultResponse(...)`, а не один общий
  конструктор.
- **Старый `schemas/result.py` удалён целиком** — на момент тикета
  оказался мёртвым кодом (0 импортов нигде в проекте после того, как
  `/result` переехал на v2 в прошлом тикете), убирать раздельно от него
  raw-поля уже было нечего.
- `frontend-result-api-contract.md` (родительская `ProOf/`) обновлён:
  добавлен `disclaimer` в пример и §3.1, `try_now`/`why` явно отмечены как
  обязательные непустые.
- Тесты: `tests/unit/test_result_v2_schema.py` (20 тестов — прямое
  конструирование Pydantic-моделей в обход ассемблера: extra-поле,
  MI+careers, неверная cardinality 8/6, `why`/`try_now` пустые, flat profile
  не 3×worth_trying, discriminator по `ResultV2Adapter`, fixtures на
  junior/middle/senior, admin-only поля не текут в student-схему — сверка
  прямо по именам полей `AdminAnalysisResultResponse`); `tests/unit/
  test_result_v2_openapi.py` (4 теста — реальный сгенерированный
  `app.openapi()`: путь `/api/v1/result/generate` отдаёт `oneOf` +
  `discriminator.propertyName == "interest_instrument"`, обе ветки
  зарегистрированы в `components/schemas`, `disclaimer` есть в обеих,
  admin-only поля не просочились). Существующие
  `test_report_v2_assembler.py`/`test_result_v2_fallback.py` не сломались
  (пересобраны без правок логики, только `try_now`-фоллбек и `disclaimer`-
  ассерт добавлены). Полный прогон — 148/148 на чистой пересборке.

## Версионирование report-кэша + Redis non-fatal — СДЕЛАНО (2026-08-12)

Реальный, уже живущий баг, найденный чтением кода до написания тестов: в
прошлом тикете `report_service.py` переехал на кэш-ключ `report:v2:{id}`, но
`assessment_shared.invalidate_retake` (чистит кэш при пересдаче) продолжал
удалять старый `report:{id}` — то есть **retake реально не чистил кэш**,
старый v2-отчёт мог продолжать отдаваться после пересдачи вплоть до TTL (24ч).

- `app/services/assessment_shared.py` — добавлен `report_cache_key()` +
  `REPORT_CACHE_KEY_PREFIX = "report:v2"`, единый источник правды. `report_service.py`
  больше не хранит свою копию префикса — `_cache_key = assessment_shared.report_cache_key`.
  `invalidate_retake` теперь удаляет ровно тот ключ, который пишет
  `report_service`. Старый нетипизированный `report:{id}` вообще нигде
  больше не адресуется ни на чтение, ни на запись — значит "не всплывает
  после rollout" выполняется структурно, а не проверкой формата на чтении.
- Redis сделан non-fatal везде на пути `/result` и retake-инвалидации:
  `report_service._cache_get`/`_cache_set` (обёртки над `redis.get`/`setex`)
  и `assessment_shared.safe_redis_delete`/`safe_redis_scan` — все ловят
  `redis.RedisError`, логируют предупреждение и продолжают через БД вместо
  падения в 500. `invalidate_retake` теперь всегда доходит до удаления
  строки `AnalysisResult` в БД даже если Redis недоступен — потеря кэша
  best-effort, потеря самой БД-записи никогда не допускается.
- Все 4 entrypoint'а retake (`assessment_service.submit_answers`,
  `question_pair_service.submit_pair_answers`,
  `motivation_pair_service.submit_pair_answers`,
  `motivation_service.submit_motivation_answers`) уже были сведены к общему
  `invalidate_retake()` в более ранней сессии — значит фикс ключа в одном
  месте чинит все четыре сразу, но это подтверждено отдельным
  параметризованным тестом по каждому entrypoint'у, а не просто "функция одна".
- Тесты: `tests/integration/test_report_cache_resilience.py` (10 тестов) —
  централизация ключа, cache hit/miss пишет/читает `report:v2:{id}`, старый
  `report:{id}` с мусорным payload'ом никак не мешает (build_report/get_report
  его игнорируют), build_report/get_report/invalidate_retake переживают
  симулированный обрыв Redis (`_BrokenRedis` — кидает `ConnectionError` на
  каждый метод) и всё равно отдают/чистят через БД, и параметризованный
  тест на все 4 retake entrypoint'а (совершают retake на уже completed
  assessment, кэш реально пуст после вызова).
- Регрессия подтверждена: временно вернул `invalidate_retake` на старый
  `f"report:{assessment_id}"` — все 4 entrypoint-теста упали именно на
  `assert await redis.get(cache_key) is None`, как и ожидалось; восстановил,
  все снова зелёные.
- Побочно: во время этого тикета в файл (`report_service.py`) параллельно
  прилетело чужое изменение — `_acquire_generation_lock()`
  (`pg_advisory_xact_lock` по `hashtext(assessment_id)`, сериализация
  конкурентных `POST /result/generate` для одного и того же assessment).
  Проверено диффом: их правка легла в отдельный, не пересекающийся со мной
  участок `build_report()` (блок "no result yet" после первого cache-miss),
  мои правки (`_cache_key`/`_cache_get`/`_cache_set`, импорт
  `assessment_shared.report_cache_key`) остались нетронуты. Конфликта не
  было, полный сьют (158 тестов) прошёл с обеими правками вместе.
- Полный прогон — 158/158 на чистой пересборке.

## Idempotency генерации + тест на неё — СДЕЛАНО (2026-08-12)

Тикет по факту застал 3 из 4 пунктов уже сделанными чужими правками (см.
"Побочно" выше и раздел про v2-форму): `_acquire_generation_lock()`
(`pg_advisory_xact_lock`) уже серилизует конкурентные генерации,
IntegrityError-хэндлер уже перечитывает и отдаёт через `_shape_response`,
`report_summary.py`/`_generate_ai_summary` уже удалены целиком (0 живых
ссылок — только два **устаревших комментария**-упоминания в
`mi_content.py`/`riasec_content.py`, поправлены на актуальные модули).
Реально не хватало только **теста**, который бы это доказывал, а не просто
предполагал:

- `tests/integration/test_result_generation_concurrency.py` — два теста
  против настоящей БД с двумя независимыми соединениями (не через
  `db_session`-фикстуру: она на одном connection/savepoint, второе реальное
  соединение по MVCC не увидело бы незакоммиченные setup-строки — поэтому
  тут ручной commit + explicit cleanup в `finally`, тот же паттерн, что и
  для другой глобальной/concurrency-специфичной логики в этом репо):
  1. `test_concurrent_generate_runs_narrative_generation_once_and_returns_identical_responses`
     — два параллельных `build_report()` (`asyncio.gather`) на один
     assessment; считает реальные вызовы `generate_report_narrative` через
     monkeypatch-обёртку (не просто "одна строка в БД" — того бы
     добился уже unique-constraint и без лока), убеждается, что вызов
     ровно один, оба ответа побайтово идентичны, в БД ровно одна строка
     `AnalysisResult`.
  2. `test_repeat_post_after_generation_does_not_regenerate` — обычный
     повторный POST после успешной генерации (с явным сбросом Redis-кэша,
     чтобы проверить именно DB-only reshape путь) не вызывает генерацию
     второй раз.
- Регрессия подтверждена: временно закомментировал вызов
  `_acquire_generation_lock()` — `test_concurrent_generate_...` упал именно
  на `assert call_count == 1` (`2 == 1`, генерация реально дублировалась),
  восстановил — снова зелёный.
- Полный прогон — 160/160 на чистой пересборке.

## Frontend-контракт /result v2 зафиксирован — СДЕЛАНО (2026-08-12)

Чисто документационный тикет — код не менялся. `../frontend-result-api-contract.md`
переписан заново (был краткий черновик времён "backend v2 ещё не реализован" —
статус обновлён на "реализовано"), сверен построчно с реальной сгенерированной
OpenAPI-схемой (`app.openapi()`, компоненты `MiResultResponse`/
`RiasecResultResponse`), а не с памятью о том, что должно было получиться:

- §3 — `interest_instrument` явно выделен как **единственный** discriminator;
  прямым текстом запрещено угадывать инструмент по возрасту/длине
  массива/виду `code`.
- §5 — cardinality `interest_map` (8 MI / 6 RIASEC) сведена в таблицу с
  допустимыми значениями `code`; явно разведены *score-derived*
  (`interest_map` — всегда полный набор категорий, из сырых нормализованных
  баллов) и *evidence-derived* (`strength_cards`/`thinking_style_notes` —
  переменная длина, только подтверждённые сигналы) поля — раньше это нигде
  не было явно объяснено, фронтенд-инженер мог по аналогии полагать, что
  `interest_map` тоже показывает только "сильные стороны".
- §4.4 — `motivation_highlights` явно описана как одна форма для
  Harter-пар (junior/middle) и MOST/LEAST-троек (senior) — что она
  унифицирована и почему.
- §6 — гарантированно непустые (`slug`/`name`/`why`/`try_now`) явно
  отделены от легитимно пустых (`matched_strengths`/`description`/
  `skills_needed`/`subjects_to_develop`/`first_steps`) полей `StudentCareer`.
- §7 — `exploration_activities` для riasec явно `[]` всегда (не
  "отсутствует или пуст согласно финальной схеме", как было расплывчато
  сформулировано раньше) — сверено с реальным `maxItems: 0` в OpenAPI.
- §9 — новый раздел: полная таблица кодов ошибок (403/404/409), явная
  формулировка "LLM/Redis сбой никогда не 5xx", idempotency-гарантия
  (§9.2, отсылка к тикету про concurrency), **rollout-примечание** (§9.3 —
  legacy `report_version=1` строки могут не пройти валидацию текущей
  v2-схемы при чтении, нужна админская регенерация — раньше это нигде не
  было явно зафиксировано как caveat) и явное разделение student/admin
  контрактов (§9.4).
- Проверка соответствия документа реальной схеме сделана инструментально, не
  на глаз: `app.openapi()` внутри контейнера, сверены `additionalProperties`,
  `required`, `minItems`/`maxItems` на обеих ветках и на `StudentCareer` —
  всё совпало с уже написанным текстом документа без правок постфактум.
- Код не менялся, весь сьют (160 тестов) прогнан для очистки совести —
  зелёный, как и ожидалось для doc-only тикета.

## Profy-Frontend адаптирован под v2-контракт — СДЕЛАНО (2026-08-12)

Не бэкенд-тикет, но напрямую следует из предыдущих: после того как `/result`
переехал на v2, `Profy-Frontend/src/pages/results/ResultsPage.tsx` начал
падать в проде с `Cannot read properties of undefined (reading
'differentiation')` — весь results-фичер был написан под удалённый
`AnalysisResultResponse` (сырые баллы, `meta.differentiation`, `code`,
`development_plan`, числовые `personality_profile`/`thinking_style`,
`careers[].match_score`/`professions`) — ни одного из этих полей в v2-ответе
больше нет.

Адаптировано (в `Profy-Frontend`, по `frontend-result-api-contract.md` и
`.claude/skills/Frontend-arch.md`):
- `shared/types/index.ts` — новые типы `ResultResponse` = `MiResultResponse
  | RiasecResultResponse` (discriminated union по `interest_instrument`,
  1:1 с бэкенд-схемой). Старый `AnalysisResultResponse`/`CareerMatch`/
  `RiasecMeta`/`DevelopmentPlan` **не удалены** — они и сейчас корректны
  для админки (`AdminAssessmentDetail.analysis_result`, отдельный
  неизменённый backend-контракт), просто больше не используются `/result`.
- `shared/api/result.ts`, `shared/store/result.ts` — переключены на
  `ResultResponse`.
- `pages/results/hooks/useResults.ts` — `isJunior` теперь берётся из
  `report.interest_instrument === 'mi'`, а не из `profile.age_group`
  (контракт §3 явно запрещает угадывать инструмент по возрасту).
- `pages/results/ResultsPage.tsx` — переписан как чистая сборка (был 497
  строк с логикой внутри), разбит на компоненты в `pages/results/components/`:
  `TopCareerHero`, `SummaryCard` (summary + disclaimer + flat-profile note
  на `is_flat_profile`, а не на пересчёте порога), `StrengthCardsSection`,
  `InterestMapSection` (level low/medium/high как непрозрачный enum — 3-точечный
  индикатор, не проценты), `CareerCard` (tier-бейдж вместо `match_score`),
  `ThinkingStyleSection`, `MotivationSection`, `ExplorationActivitiesSection`
  (новая секция для junior). Секция "Твой характер" (сырой Big Five) и "Что
  усилить/подтянуть" (`development_plan`) удалены целиком — их нет в
  контракте, соответствующий текст уже внутри `strength_cards`/`summary`.
- `pages/results/DirectionDetailPage.tsx` — `describeCareerFit(report.code,
  direction)` заменён на `direction.why` (уже готовый текст от бэкенда);
  блок "Профессии" (`direction.professions`) удалён — поля `professions` в
  `StudentCareer` v2 не существует вообще; добавлен блок `try_now`
  (гарантированно непустой, раньше не было в контракте).
- `shared/lib/riasecMatch.ts` — удалён целиком (мёртвый код, `career.why`
  от бэкенда полностью его заменяет).
- Верифицировано: `npm run typecheck`/`npm run build` чистые; полный e2e
  прогон через реальный `/api/v1` (register→verify→login→profile→assessment→
  answers→motivation→`/result/generate`) для senior (riasec, flat profile →
  ровно 3 `worth_trying` careers) и junior (mi, 8 interest_map, careers=[],
  непустые exploration_activities) — оба ответа побайтово совпали с новыми
  TS-типами. Ручная проверка в браузере не проводилась — в этой сессии нет
  инструмента браузерной автоматизации; e2e-проверка через реальный API
  сделана как замена, но `npm run dev` + просмотр `/results` в браузере
  человеком до мержа не будет лишним.

## Тестовое покрытие редизайна + приёмка — СДЕЛАНО (2026-08-12)

Тикет на покрытие тестами и приёмку. Большая часть отдельных механизмов
(idempotency, кэш, discriminated schema, narrative validator) уже была
покрыта в предыдущих тикетах — здесь закрыты реальные пробелы: end-to-end
age matrix на настоящих данных (а не только на монки), retake-очистка по
всем 4 путям, реальный migration round-trip и снапшоты контракта.

**Обязательная age matrix** — `tests/integration/test_age_matrix_full_flow.py`
(4 теста). Ключевое отличие от всех более ранних тестов `/result`: здесь
реально создаются `Question`/`QuestionPair`/`UserResponse`/`MotivationPair(Response)`/
`MotivationStatement(Response)` строки и отправляются через настоящие
сервисы (`assessment_service.submit_answers`, `question_pair_service.
submit_pair_answers`, `motivation_pair_service`/`motivation_service`), а не
собирается сразу готовый ответ. Единственное, что монки патчат — счётчики
глобальных total'ов (`question_counts`/`facet_counts`, completion gate) по
уже задокументированной в этом файле причине (общая dev-БД, тотал считает
все строки в таблице, а не только добавленные тестом) — сама скоринговая
математика и сборка ответа выполняются по-настоящему.
- Junior: MI (plain Likert) + Big Five (прямой ответ **и** через
  `question_pair_service` — тикет явно просил проверить оба пути) + Harter
  pairs → 8 MI-интересов, доминантная категория `level="high"`, `careers=[]`,
  непустые `exploration_activities`. Отдельно подтверждено (переиспользуя
  логику уже существующего `test_junior_likert_total_excludes_stale_riasec_but_counts_mi`
  из `test_report_completion_gate.py`), что junior-тег RIASEC-вопрос не
  двигает total.
- Junior incomplete Harter → 409, `assessment.status` не меняется (пин
  поверх реального DB-ряда, не только на уровне счётчиков).
- Middle: RIASEC + Big Five/question pairs + Harter → 6 интересов,
  `careers` с монотонным `rank`, непустые `why`/`try_now`, единая форма
  `motivation_highlights`.
- Senior: RIASEC + Big Five + тройки MOST/LEAST → тот же публичный
  `motivation_highlights`; **проверено прямой атакой**: для того же
  assessment одновременно существует Harter-pair-ответ (`money`) и
  triplet-ответ (`creation`) — итоговый текст обязан содержать только
  triplet-категорию. Регрессия подтверждена: временно заставил senior идти
  по ветке `motivation_pair_service` — тест упал именно на утечке
  "материальный результат" в тексте, восстановил.

**Retake full cleanup** — `tests/integration/test_retake_full_cleanup.py`
(4 теста, по одному на entrypoint: ordinary answers, question pairs, Harter
pairs, senior triplets). В отличие от уже существовавших тестов
(`test_report_cache_resilience.py` проверял только report-кэш,
`test_goal_roadmap_retake_invalidation.py` — только `invalidate_goal_roadmap`
в изоляции), здесь на каждый entrypoint высеиваются **все** артефакты сразу
(`AnalysisResult`, `DirectionInquiry`, `DirectionRoadmap`, `Roadmap` + все
4 Redis-ключа) и проверяется, что retake реально удаляет всё, не только
что-то одно. Регрессия подтверждена: временно отключил
`invalidate_goal_roadmap` внутри `invalidate_retake` — все 4 теста упали
именно на "goal_roadmap_row row survived retake", восстановил.

**Migration upgrade/downgrade round-trip** —
`tests/integration/test_alembic_migration_roundtrip.py` (2 теста). Против
одноразовой throwaway-БД на том же Postgres-сервере (создаётся/удаляется
самим тестом через `asyncpg`, никогда не трогает общую dev-БД — `alembic
downgrade` дропает колонки/таблицы, делать это на БД, которой пользуются
остальные тесты, было бы разрушительно). `alembic` вызывается как
настоящий CLI (subprocess) с `DATABASE_URL`, переопределённым через
окружение. Второй тест — что `alembic heads` всегда даёт ровно одну голову
(прямой регрессионный guard на класс бага, который уже был: расхождение
веток с независимо появившейся миграцией `0040`, см. "Расхождение
веток — РЕШЕНО" в начале файла).

Тест реально нашёл и я исправил **2 живых бага** в истории миграций (полный
`downgrade` от head до base ни разу раньше не прогонялся целиком):
- `0033_direct_profession_program_mapping.py`: `downgrade()` восстанавливал
  колонку `programs.direction_slug`, но не восстанавливал её индекс
  `ix_programs_direction_slug` — падало на попытке миграции `0011` его
  удалить (объекта уже не существовало).
- `0024_riasec_migration.py`: `downgrade()` восстанавливал колонки
  `questions.block`/`age_group`, но не восстанавливал 3 индекса
  (`ix_questions_block`, `ix_questions_age_group`, `ix_questions_block_age_group`),
  которые создавал `0005` — та же природа бага.

Оба исправлены точечно (добавлен `op.create_index(...)` в соответствующий
`downgrade()`), без изменения `upgrade()` — поведение прод-миграций (все уже
применены по цепочке `upgrade`) не затронуто, только реальная
воспроизводимость `downgrade`, которая раньше нигде не проверялась.

**OpenAPI/student/admin снапшоты** — два файла:
- `tests/unit/test_openapi_schema_snapshot.py` (4 теста) — нормализованный
  (без auto-generated `title`/`description`, которые шумят при не относящихся
  к контракту правках докстрингов) снимок `properties`/`required`/
  `additionalProperties`/constraints для `MiResultResponse`,
  `RiasecResultResponse`, `StudentCareer`, `AdminAnalysisResultResponse` —
  файлы в `tests/snapshots/openapi_*.json`.
- `tests/unit/test_result_v2_example_snapshots.py` (3 теста) — конкретный
  пример ответа на junior/middle/senior (переиспользует fixture-билдеры из
  `test_result_v2_schema.py`, не второй дрейфующий набор "как выглядит
  валидный ответ"), `assessment_id`/`created_at` зафиксированы для
  детерминизма — `tests/snapshots/result_v2_example_*.json`.

Оба типа снапшотов проверены на то, что реально ловят дрейф (не просто
всегда проходят): точечно испортил значение в одном JSON-файле, тест упал
с понятным diff, восстановил.

Полный прогон после всех правок — **177/177** на чистой пересборке.

## Ручная приёмка (2026-08-12)

Прогнано 24 синтетических профиля (8 на возраст — по одному на каждую из 8
MI-категорий для junior; по одному на каждую из 6 RIASEC-категорий +
flat-profile + low-signal вариант для middle и senior) через настоящий
`report_service.build_report()` с явно выключенным LLM (детерминированный
fallback — без реальных токенов; см. ниже про LLM-путь). Скрипт — разовый,
не сохранён в репозитории (создавал/удалял собственные строки в общей
dev-БД, следил за очисткой; финальная проверка — БД вернулась к базовой
строке: 5 users, 314 questions, 18 motivation_pairs, 36 motivation_statements).

| Проверка | junior (8/8) | middle (8/8) | senior (8/8) |
|---|---|---|---|
| Cardinality (8 MI / 6 RIASEC) | ✅ | ✅ | ✅ |
| `careers=[]` (junior) / ранжированные careers (middle/senior) | ✅ | ✅ | ✅ |
| Сырые числа/`%` в narrative-тексте (summary/cards/motivation/why/try_now) | 0 из 8 | 0 из 8 | 0 из 8 |
| Запрещённая лексика (Приложение C) | 0 из 8 | 0 из 8 | 0 из 8 |
| Career-давление у junior (термины профессия/карьера/вуз/...) | 0 из 8 | — | — |
| Язык (доля кириллицы в тексте) | ~1.0 | ~1.0 | ~1.0 |

Один ложный сигнал по пути разобран и задокументирован: черновая версия
скрипта считала цифрой всё что угодно в тексте ответа, включая
DB-фактические поля карьеры (`career.name`, `skills_needed` и т.п.) —
поймала `"Аниматор (2D/3D)"` из реального каталога `directions`. Это не
баг: правило "без чисел" (ТЗ §18.3) относится к narrative-тексту
(summary/cards/motivation/why/try_now), а не к фактическим данным из БД
(имя направления, требуемые навыки) — они по определению могут содержать
техническую нотацию с цифрами. Скрипт поправлен различать эти два
класса полей; после исправления — 0 ложных срабатываний.

**LLM-путь не проверялся вживую** (эта сессия сознательно не тратила
реальные токены на 24 профиля без явного запроса пользователя) — вся
ручная приёмка выше прошла через deterministic fallback
(`report_narrative_fallback.py`), который уже отдельно протестирован на
то, что всегда проходит `report_narrative_validator.validate()`
(`tests/unit/test_report_narrative_fallback.py`). Если нужна очная
проверка реальных LLM-ответов на нескольких профилях — отдельный
осознанный шаг с одобрения пользователя (стоимость токенов).

## Дубликат "Стиль мышления" внутри "Сильных сторон" — СДЕЛАНО (2026-08-12)

Найдено по жалобе пользователя на скриншоте `/results`: карточки вида
"Креативное мышление"/"Стратегическое мышление" внутри блока "Сильные
стороны", а затем **дословно тот же текст** ещё раз в отдельном разделе
"Стиль мышления". Не догадка — воспроизведено кодом:
`report_narrative_fallback._strength_cards()` брала первые N элементов из
**общего** плоского `context.evidence` без фильтра по типу; если
интересов/черт характера/мотивации набиралось меньше 7, в добор шли
`thinking_style`-факты — те же самые, что отдельно уходят в
`thinking_style_notes`. То же самое было верно для LLM-пути:
`_check_strength_card_count` в валидаторе считал "доступные" факты по
всему `context.evidence`, не исключая thinking_style, так что ничего не
мешало модели (и не мешало cardinality-проверке) процитировать
thinking_style evidence_id внутри strength_cards.

Заодно нашлась причина по ТЗ: `TZ_Profi.md` §18.2 п.2 ("Сильные стороны")
и п.4 ("Стиль мышления") — два разных раздела, и п.4 явно требует
**конкретные примеры задач, а не абстракции**. В коде на каждый стиль
мышления была только одна фраза (`thinking_style_content.py`), общая для
обоих разделов — отсюда и структурная невозможность развести тексты.

Сделано:
- `report_narrative_context.STRENGTH_CARD_EXCLUDED_SOURCE_TYPES = {"thinking_style"}`
  — общая для fallback/валидатора/промпта константа.
- `report_narrative_fallback._strength_cards()` — фильтрует пул по этой
  константе перед `[:7]`.
- `report_narrative_validator.py` — `_check_strength_card_count` считает
  "доступные" факты без thinking_style; новая `_check_strength_card_sources`
  жёстко отклоняет ответ, если strength_card всё равно сослалась на
  thinking_style evidence_id (структурная гарантия, а не только промпт).
- `app/prompts/report_narrative.py` — системный промпт прямо запрещает
  использовать thinking_style evidence в strength_cards.
- `thinking_style_content.THINKING_STYLE_NOTES` — переписаны с добавлением
  конкретного примера задачи на каждый стиль (TZ §18.2 п.4), текст теперь
  умышленно отличается от общей формулировки сильной стороны для той же
  черты — дублирование теперь невозможно даже по смыслу, не только по факту
  исключения из пула.
- Тесты: новый regression-тест в `test_report_narrative_fallback.py`
  (thinking_style пробуют "добить" карточки при малом пуле — подтверждено,
  что не просачивается), новый тест в `test_report_narrative_validator.py`
  (код `strength_card_excluded_source_leak` — переименован позже в тот же
  день, когда то же исключение расширили на мотивацию, см. следующий
  раздел), новый тест в
  `test_report_narrative_prompt.py`. Полный прогон — 180/180.
- Проверено вживую через реальный `/result/generate` (не только тестами):
  `strength_cards`/`thinking_style_notes` пересечение текста — пустое
  множество.
- Regression-proof: временно откатил фильтр внутри контейнера (хостовый
  файл не трогал — образ не bind-mount), получил ожидаемые 3 упавших теста
  (включая независимое срабатывание валидатора), восстановил, пересобрал
  образ с нуля, снова 180/180.

Не сделано в рамках этого фикса (осознанно меньший скоуп, см. обсуждение
с пользователем): визуальный редизайн карточек "Сильные стороны" на
фронтенде (иконки/цвет/группировка) и переход `/result` на постраничную
навигацию по экранам (`TZ_Profi.md` §18.1) — оба отдельные, более крупные
задачи, ждут своего тикета.

## Мотивация дублировалась так же, как стиль мышления + непонятные title — СДЕЛАНО (2026-08-12)

Пользователь показал реальный результат `test@testmail.com` (взят напрямую
через `report_service.get_report`, не выдуман) — предыдущий фикс закрыл
только `thinking_style`, но точно та же архитектурная проблема была верна
и для мотивации: в "Сильные стороны" три раза подряд шёл заголовок "Что
тебя драйвит", а ниже — отдельный раздел "Что тебя драйвит" с тем же
текстом ещё раз. Плюс отдельная, более глубокая жалоба: карточки выглядели
"неинтересно" и "плохо описаны" — заголовки были общими категориями
("Тебе интересно", "Твой характер", "Даётся легко"), а не конкретными
наблюдениями, как того явно требует и `TZ_Profi.md` §18.2 п.2, и
`result-report-redesign-plan.md` (пример из документа: «Ты замечаешь,
когда что-то не работает, и хочешь разобраться почему»).

Сделано:
- `STRENGTH_CARD_EXCLUDED_SOURCE_TYPES` расширен до
  `{"thinking_style", "motivation"}` — то же исключение из пула
  "сильных сторон", что уже было сделано для стиля мышления, теперь и для
  мотивации. Валидатор (`_check_strength_card_count`,
  `_check_strength_card_sources` — переименована в
  `strength_card_excluded_source_leak`, т.к. теперь общая для обоих типов)
  и LLM-промпт обновлены синхронно.
- **Реальная причина "непонятных title"**: `report_narrative_fallback.
  _strength_cards()` использовала общую категорийную метку как `title`
  ("Тебе интересно"/"Твой характер"/...) и саму конкретную фразу как
  `description` — наоборот от того, что уже делает LLM-путь и что требует
  ТЗ. Поменял местами: `title` = сама конкретная формулировка (например,
  "Любишь докапываться до сути и разбираться, как всё устроено"),
  `description` = короткое заземляющее предложение по типу источника
  ("Это заметно по тому, какие ответы ты выбирал(а) в тесте."). Теперь у
  каждой карточки свой уникальный title, даже когда несколько карточек
  одного типа (было такое же дублирование title, что и с мотивацией, только
  тише — не дословный повтор блока, а повтор одного и того же слова у
  разных карточек).
- Тесты: новый тест на утечку мотивации в fallback (зеркало
  thinking_style-теста), новый тест
  `test_strength_card_citing_motivation_evidence_is_rejected` в валидаторе,
  новый тест на то, что title = конкретная фраза, а не общая категория.
  Обновлены счётчики в существующих тестах (`_senior_context`/`_junior_context`
  дают меньше "доступных" карточек теперь, когда мотивация тоже исключена
  — пересчитано и задокументировано в комментариях). Полный прогон — 184/184,
  regression-proof прогнан (временный откат внутри контейнера → 3 ожидаемых
  падения → восстановление → чистая пересборка → 184/184).
- Проверено вживую: свежая генерация даёт 6 уникальных title в
  strength_cards, ни одного повторного слова, пересечение с
  motivation_highlights/thinking_style_notes — пустое.
- **Важно**: уже сгенерированные и сохранённые отчёты (включая тот, что
  смотрел пользователь у `test@testmail.com`) содержат СТАРЫЙ текст —
  `/result` генерируется один раз и хранится бессрочно (`TZ_Profi.md`
  §17.2), фикс контента применяется только к новым генерациям. Чтобы
  увидеть новый текст на уже пройденном тесте, нужен админский триггер
  регенерации (за пределами этой задачи) либо новый assessment.
- **Frontend**: заодно исправлен порядок разделов на `/results` — раньше
  "Подходящие профессии" шли перед "Картой интересов", из-за чего карта
  интересов оказывалась в самом низу длинной страницы и терялась (жалоба
  "карта интересов вообще нету" — на самом деле данные были, но визуально
  не были заметны). Новый порядок соответствует `result-report-redesign-
  plan.md`/`TZ_Profi.md` §18.2 дословно: резюме → сильные стороны → карта
  интересов → стиль мышления → мотивация → профессии/занятия (последними).
  Заодно убран отдельный "hero"-блок с топ-профессией (моё собственное
  добавление, не из ТЗ/плана) — он вводил в заблуждение при
  `is_flat_profile=true`: подсвечивал одну профессию как будто она лучше
  других, хотя у всех трёх при плоском профиле дословно одинаковый текст
  `why`/`try_now`. `TopCareerHero.tsx` удалён как более не используемый.
  `npm run typecheck`/`build` — чистые.

## КРИТИЧНО: LLM-путь почти никогда не проходил валидацию для middle/senior — НАЙДЕНО И ИСПРАВЛЕНО (2026-08-12)

По запросу пользователя перечитать `Рефакторинг.md` и разобрать, почему
результат "читается глупо" — стал проверять не только контент-баги (см.
раздел выше про title/мотивацию), а сам факт: доходит ли вообще
персонализированный ИИ-текст до пользователя, или всё это время все видели
детерминированный шаблон.

**Проверил вживую, не по догадке**: вызвал `report_narrative_service.
generate_report_narrative()` напрямую с реальным LLM (в этом окружении
`LLM_ENABLED=true`, рабочий ключ) на нескольких реалистичных сценариях
middle/senior. Результат ДО фикса: **0 из 3** сценариев проходили валидацию
— все 3 попытки (1 + 2 retry) проваливались, каждый раз с
`career_narrative_evidence` (LLM оставлял `evidence_ids` пустым в
`career_narrative`), плюс сегодняшние `strength_card_count`/
`strength_card_excluded_source_leak`. Junior (у которого career_narrative
всегда `[]`) проходил с первой попытки. То есть **middle/senior практически
никогда не получали живой ИИ-текст** — только статичный шаблон, слово в
слово одинаковый для всех. Это и есть настоящая причина "читается
глупо/неинтересно": не столько формулировки, сколько то, что персонализация
(TZ_Profi.md §17.1: "два ребёнка с похожими скорами должны получить заметно
разные тексты") фактически не работала вообще, при этом каждый вызов уже
тратил реальные деньги на 3 неудачные попытки.

**Корневая причина**: retry был "слепой" — `report_narrative_service.
generate_report_narrative()` формировал `messages` один раз и переиспользовал
идентичный промпт на всех 3 попытках. Систематическую ошибку модели (она
стабильно не проставляет `evidence_ids` для `career_narrative`) слепой повтор
не лечит — модель просто повторяет ту же ошибку.

Сделано:
1. `app/prompts/report_narrative.py` — усилены инструкции по
   `career_narrative` для middle/senior (явное требование `evidence_ids` с
   примером) и добавлен блок "ЧЕК-ЛИСТ ПЕРЕД ОТПРАВКОЙ" в самом конце
   системного промпта (перед каталогом фактов) — самые частые нарушения
   продублированы там же, где модель их прочитает последними перед
   генерацией (recency).
2. `app/services/report_narrative_service.py` — retry стал **корректирующим**:
   после неудачной попытки в диалог добавляется её собственный ответ +
   человеко-читаемое объяснение, что конкретно не так и что исправить
   (`_correction_message`/`_CORRECTION_HINTS` — код ошибки переводится в
   конкретную инструкцию на русском, а не просто "code: detail"; голого
   `code: detail` оказалось недостаточно — проверено вживую, модель не
   самокорректировалась, пока подсказка не стала явной инструкцией).
   `issue.detail` в переписке с моделью — это нормально (это её собственный
   контекст для исправления), логирование по-прежнему только кодами.
3. Тест `test_retry_feeds_the_previous_failure_back_to_the_model` — ловит
   именно это: подтверждено regression-proof (временно отключил блок
   добавления correction-сообщения внутри контейнера → тест упал именно там,
   где ожидалось → восстановил → пересобрал → 185/185).

**Результат после фикса**: 5 из 5 новых живых сценариев (senior и middle,
разные evidence-профили) прошли с реальным ИИ-текстом, большинство — за 1-2
попытки вместо исчерпания всех 3. Тексты теперь по-настоящему разные между
сценариями — не статичный шаблон.

## Живой баг: create_assessment штамповал брошенную попытку как completed — НАЙДЕНО И ИСПРАВЛЕНО (2026-08-12)

Не тикет — запрос от пользователя разобрать сломанную генерацию `/result`
для `test@testmail.com`. Воспроизвёл вживую (не по логам — контейнер
пересобирался много раз за сессию, старые логи не сохранились):

- `GET /result/{id}` → 404, `POST /result/generate` → 409, хотя
  `assessment.status == 'completed'` в БД.
- Пересчёт напрямую: Likert (RIASEC+BigFive) — 182/182 отвечено; Harter-пары
  мотивации — **0/18**. Тест реально не пройден, но помечен завершённым.

**Корень** — `app/services/assessment_service.py`, `create_assessment()`:
при старте новой попытки, если у профиля уже висела брошенная `in_progress`
запись, код безусловно штамповал её `AssessmentStatus.completed` (без
проверки реальной завершённости) — вероятно, чтобы не нарушить инвариант
«не больше одной `in_progress` записи на профиль» (иначе
`get_current_assessment()` упал бы на `scalar_one_or_none()`). Но ценой
того, что `completed` перестаёт значить «тест реально пройден» везде, где
на это полагается остальной код.

Проверил все места, которые пишут `AssessmentStatus.completed` — их 3:
`motivation_service.py`/`motivation_pair_service.py` (оба гейтят на
`mot_completed and likert_completed`) и `report_service.py` (только после
`_assert_assessment_complete()`). Все три корректны. `create_assessment()`
был единственным небезопасным писателем.

**Исправлено** (после согласования с пользователем — обсуждали новый статус
`abandoned` с миграцией под enum, выбрали более простой вариант): брошенная
`in_progress`-попытка теперь **удаляется**, а не штампуется — тот же
паттерн «отбросить старые артефакты при чистом старте», что уже
используется в `assessment_shared.invalidate_retake`. Каскад по FK
(`ondelete="CASCADE"`) сам подчищает её `UserResponse`/`MotivationPairResponse`/
`MotivationResponse`.

- Тест: `tests/integration/test_create_assessment_abandons_incomplete_attempt.py`
  (2 теста) — брошенная незавершённая попытка удаляется (не остаётся
  `completed`-сиротой), её `UserResponse` тоже уходит каскадом; новая
  попытка после этого — единственная `in_progress` запись у профиля.
  Регрессия подтверждена: вернул старое поведение — оба теста упали именно
  на "must be deleted, not stamped completed" / "only the new assessment
  should remain" (`2 == 1`), восстановил — снова зелёные.
- Ручной data-fix для самого `test@testmail.com`: assessment `8365e0b7...`
  вручную сброшен обратно в `in_progress` (`completed_at = NULL`) —
  проверено через `get_current_assessment()`, состояние теперь честное
  (182/182 Likert, 0/18 мотивации). Пользователю остаётся ответить на 18
  Harter-пар, дальше `/result/generate` отработает штатно.
- Полный прогон — 182/182 на чистой пересборке.

## Что ещё НЕ сделано (сам редизайн)

- `career_narrative` из narrative-пайплайна нигде не используется в
  итоговом v2-ответе (см. выше) — сознательно: `careers` строится из
  реальных `Direction`. Если продукту нужен LLM-текст именно на уровне
  конкретной профессии/вуза — это отдельная, ещё не написанная задача.
- `is_flat_profile`/матрица направлений — пороги захардкожены (не
  admin-настраиваемые), как и было отмечено в TZ §16.4 как желаемое, но не
  обязательное для MVP.
- Локализация (`kk`/`en`) — валидатор и весь pipeline рассчитаны только на
  `ru` (`_check_language` в `report_narrative_validator.py` пропускает
  проверку для остальных языков, а не проверяет их). **Продуктовое решение
  (2026-08-12): пока не нужна, только `ru`** — не открытый пункт, не делать
  без отдельного запроса.

Это и есть содержание оставшихся RS-тикетов.

## Глубокий аудит "почему результат скучный/дублирует" — НАЙДЕНО, НЕ ИСПРАВЛЕНО (2026-08-13)

Пользователь принёс `my-deep-analysis.md` (свои живые наблюдения по
junior/middle/senior реальным аккаунтам) и попросил проверить структуру
целиком против `Рефакторинг.md`/TZ_Profi.md, не трогая ничего, что можно
поправить через UI/копирайт фронта. Проверено на реальных данных (БД,
живой код), не по догадке:

- **НОВЫЙ баг, не тот же что чинили 2026-08-12**: `report_narrative_validator.
  _check_strength_card_count` проверяет только суммарное количество
  strength_cards, но НЕ проверяет, что каждая карточка ссылается на свой
  уникальный `evidence_id`. LLM-путь (в свете вчерашнего фикса надёжности
  теперь реально долетает до пользователя гораздо чаще) может законно
  выпустить 3 карточки, все ссылающиеся на один и тот же
  `subject_easy:Информатика`, перефразированные по-разному — ровно то, что
  пользователь увидел живьём ("3 раза Информатика" у senior). Нужно:
  добавить проверку в валидатор (`strength_card_duplicate_evidence` —
  каждый source_id встречается не более чем в одной карточке
  strength_cards) + усилить промпт явным запретом.
- **НОВЫЙ баг**: `app/services/motivation_content.py:33` `highlight_phrases()`
  жёстко добавляет префикс `"Тебя больше всего драйвит — "` к КАЖДОМУ
  элементу списка — если топ-мотиваторов 3, все 3 строки начинаются с
  одинаковой фразы. Это backend-контент, не UI. Прямая причина жалобы
  "не чтобы на каждой колонке было «Тебя больше драйвит»".
- **Уточнение по уже исправленному 2026-08-12**: пример из
  `my-deep-analysis.md` про "перевёрнутый" title/description у senior —
  это старый закешированный отчёт (генерируется один раз и не
  перегенерируется, TZ §17.2), фикс title/description уже применён для
  новых генераций. Не открытый баг.
- **Структурная проблема, подтверждена на живых данных**: карьерный
  матчинг (`riasec_service.matched_careers`/`career_match_score`) ранжирует
  все 92 строки `directions` ИСКЛЮЧИТЕЛЬНО по перекрытию с топ-3 буквами
  RIASEC (`report_service.py` строка ~314 `code = riasec_service.top_code(...)`
  → `matched_careers(code, db)`). Он вообще не смотрит на
  `subjects_liked`/`subjects_easy`/personality/artifacts — те факты, что
  идут в strength_cards. Поэтому пользователь видит карточку "Информатика"
  среди сильных сторон, а затем профессии типа Агроном/Авиадиспетчер/
  Модельер без единого объяснения связи. Проверено на реальных строках БД:
  `Авиадиспетчер` (`aviadispetcher`, holland_code=SER), `Агроном`
  (`agronom`, IRS), `Модельер` (`modeler`, ASR) — ранжируются, если топ-код
  содержит I/R, что и происходит. Это не баг ранжирования, а архитектурный
  разрыв: два независимых источника фактов (RIASEC-скоринг для карьер,
  весь остальной evidence-каталог для нарратива) никак не согласованы.
- **Content-gap, подтверждён SQL-запросом, НЕ баг кода**: из 92 строк
  `directions` — `description`, `first_steps`, `skills_needed`,
  `subjects_to_develop` пустые у ВСЕХ 92 (0/92 по каждому полю). Это
  соответствует докстрингу `app/models/direction.py:22-27` — новый
  каталог профессий (RIASEC-миграция) сознательно завезён только с
  name+code, наполнение контента — отдельная задача. `Рефакторинг.md`
  сам явно выносит "Direction content" в отдельный Backlog (раздел
  Scope), вне RS-1…RS-15. Поэтому "почему все профессии звучат одинаково
  скучно" — не баг наших RS-тикетов, а неисполненный контент-беклог:
  `why`/`try_now` у каждой карьеры всегда падают на один и тот же
  нейтральный fallback (`NEUTRAL_CAREER_WHY`/`NEUTRAL_TRY_NOW`), потому
  что `first_steps` пуст буквально у каждой строки.
- Всё, что пользователь просил переименовать/убрать и что реально
  является UI/копирайтом фронта (не тронуто по прямому запросу
  пользователя "не трогай UI"): заголовок секции "Твой профиль RIASEC"
  (`InterestMapSection.tsx:21-22` — буквально показывает жаргон "RIASEC"
  ребёнку), заголовок "Что тебя драйвит" (`MotivationSection.tsx:13`),
  кнопка/блок "Подходит ли мне это направление?" (`CareerCard.tsx:61`,
  `DirectionDetailPage.tsx:192` — пользователь просил убрать саму эту
  логику, это уже не копирайт, а решение по фиче `direction_inquiry_service.py`
  — нужно отдельное продуктовое решение, не мелкая правка).

Ничего из этого раздела ещё не исправлено — доведено до пользователя как
анализ с предложениями, ждём приоритезации перед реализацией.

## Два бага из аудита выше — ИСПРАВЛЕНО (2026-08-13)

Пользователь дал общее "начинай решать проблемы" — начал с пп.1-2 из
`result-quality-fixes.md` (рекомендованный там порядок: маленькие,
безопасные, backend-only фиксы без продуктовых решений). Остальное
(карьерный матчинг, контент направлений, продуктовые решения по
inquiry-фиче) — по-прежнему открыто, не начато.

- **Дубли evidence в strength_cards**: добавлена
  `_check_strength_card_duplicate_evidence` в
  `report_narrative_validator.py` — источник (source_id) больше не может
  быть процитирован более чем в одной карточке strength_cards. Промпт
  (`app/prompts/report_narrative.py`) усилен явным пунктом в чек-листе и в
  описании strength_cards. `_CORRECTION_HINTS` в
  `report_narrative_service.py` дополнен переводом нового кода на русский
  для corrective retry. Тесты: `test_strength_card_citing_the_same_
  evidence_as_another_card_is_rejected`,
  `test_strength_card_with_multiple_distinct_evidence_ids_is_not_flagged`
  в `tests/unit/test_report_narrative_validator.py`. Regression-proofed:
  временно вернул `[]` из новой функции внутри контейнера (хост не
  трогал) — новый тест упал как ожидалось, восстановил, пересобрал —
  снова зелено.
- **Жёсткий повторяющийся префикс в мотивации**: `motivation_content.
  highlight_phrases()` (`app/services/motivation_content.py:32-37`)
  больше не приклеивает `"Тебя больше всего драйвит — "` к каждому
  элементу — теперь список голых фраз с заглавной буквы (фронт уже
  рендерит их по одной карточке на фразу, так что это именно то, что
  нужно). `_motivation_narrative()` в `report_narrative_fallback.py`
  (не показывается студенту напрямую, но валидируется и хранится)
  соответственно перестал наивно склеивать фразы через пробел — теперь
  через `_join_ru` в одно грамматически связное предложение. Новые тесты:
  `tests/unit/test_motivation_content.py` (3 теста),
  `test_motivation_narrative_joins_multiple_drivers_into_one_readable_
  sentence` в `test_report_narrative_fallback.py`. Обновлена одна
  интеграционная проверка (`test_age_matrix_full_flow.py:378`) — она была
  case-sensitive к слову "создава", а новая фраза начинается с заглавной
  "Создавать" (раньше было в середине предложения после префикса) —
  сделал сравнение case-insensitive, это не ослабление теста, просто
  снятие случайной зависимости от старой (багованной) капитализации.
- Живая проверка (не только юнит-тесты): скрипт внутри контейнера
  прогнал `build_fallback_narrative`/`highlight_phrases` на реалистичном
  evidence-наборе — `motivation_highlights` вышли как 3 самостоятельные
  фразы без повтора, `motivation_narrative.description` — одно связное
  предложение "Заниматься тем, что по-настоящему интересно, создавать
  что-то своё и работать в сильной команде.", `validate()` — `[]`.
- 191/191 полный набор тестов (было 185 до сегодняшних тестов + новые).
- **Не сделано, всё ещё открыто**: пп.3-6 `result-quality-fixes.md` —
  разрыв карьерного матчинга и остального evidence, пустой контент 92
  направлений, продуктовые решения по inquiry-фиче и по наполнению
  контента. См. этот файл для деталей и предложенных вариантов решения.

## П.3 вариант A (текст "why" для карьер) — СДЕЛАНО (2026-08-13)

Пользователь сказал "просто следуй плану" — сделал п.3 вариант A, следующий
пункт рекомендованного порядка после пп.1-2. `NEUTRAL_CAREER_WHY`
(`app/services/riasec_content.py`) переписан с расплывчатого "хорошо
сочетается с тем, что уже проявилось в твоих ответах" (звучит как реальное
совпадение) на честное "подобрано по общей картине теста интересов, а не по
одной конкретной сильной стороне". 191/191 тестов зелёные без изменений в
тестах (существующий тест сравнивает с константой, не с литеральной
строкой).

**Важно: это НЕ полностью закрывает живой пример пользователя**
(Агроном/Авиадиспетчер/Модельер при evidence "Информатика") — там
`matched_strengths` был непустым (буква R совпадала), значит в дело шёл
не `NEUTRAL_CAREER_WHY`, а ветка "Совпадает с тем, что у тебя выражено:
...". Вариант A закрывает только случай нулевого пересечения с RIASEC.
Настоящая причина (RIASEC-матчинг не видит subject/personality evidence)
остаётся открытой — это варианты B/C в `result-quality-fixes.md` §3,
которые требуют либо наполнения контента направлений (п.4), либо
пересмотра архитектуры матчинга (отдельная задача).

**Дальше по плану — упёрлись в продуктовые решения (п.6), не автономно
решаемые**: нужно явное решение пользователя, убирать ли inquiry-фичу
полностью и как подходить к наполнению контента 92 направлений (вручную/
LLM+ревью/гибрид) — без этого пп.4 и п.3C не начать осмысленно.

## П.6 решения получены — обе задачи в работе (2026-08-13)

Пользователь ответил на оба вопроса:
1. Inquiry-фичу — оказалось, что `direction_roadmap` жёстко зависит от неё
   (backend гейтит генерацию плана на завершённый inquiry,
   `roadmap_builder.py`). Пользователь подтвердил: roadmap будет
   перестроен позже по-другому, поэтому убрали только UI-вход со страницы
   результата, backend/опросник/roadmap-гейт не трогали — см. запись выше
   про "убрали кнопку".
2. Контент 92 направлений — "LLM-генерация + моя проверка".

**Сделано**: `scripts/generate_direction_content.py` — генерирует
description/skills_needed/subjects_to_develop/first_steps через
`llm_client.complete_json` (тот же клиент, что и report_narrative), пишет
в `scripts/direction_content_review.json` (НЕ в БД напрямую). Прогнан на
всех 92 строках: **92 сгенерировано, 0 ошибок, 2 автопометки** (обе —
ложные срабатывания эвристики "цифра в тексте": "3D-визуализациями" у
архитектора и "детей в возрасте от 3 до 7 лет" у воспитателя — реальный
факт, не выдумка). Смок-тест на 3 направлениях перед полным прогоном
(Агроном/Авиадиспетчер/Модельер — те самые из живой жалобы пользователя)
показал конкретный, не шаблонный текст без выдуманных вузов/цифр/зарплат.

Собрана HTML-страница для ревью (сгруппировано по RIASEC-категориям,
поиск, фильтр по категории/пометкам) — опубликована как Artifact,
ссылка отправлена пользователю.

## Ревью пройдено, контент применён в БД (2026-08-13)

Пользователь: "мне нравится всё" — с одной правкой: блок «Первые шаги» (3
пункта) убрать, `try_now` оставить (единственная конкретная фраза "что
попробовать прямо сейчас" — уже была отдельной от 3-шагового блока).

**Убрано из student-контракта** (не из БД — сами 3 шага в БД остались,
просто больше не отдаются студенту отдельным списком):
- `app/schemas/result_v2.py`: `StudentCareer.first_steps` поле удалено.
- `app/services/report_v2_assembler.py`: `build_riasec_careers()` больше
  не передаёт `first_steps=` в `StudentCareer(...)` — `try_now` по-прежнему
  берёт `first_steps[0]` из сырого dict направления.
- Фронт: `Profy-Frontend/src/pages/results/DirectionDetailPage.tsx` — блок
  "Первые шаги" (карточки 1/2/3) удалён; `shared/types/index.ts`:
  `StudentCareer.first_steps` убран из типа.
- `Profy-Frontend/docs/result-api-contract.md` обновлён (явно
  задокументировано, что поле удалено и почему).
- 3 снапшот-теста (`result_v2_example_middle/senior.json`,
  `openapi_student_career.json`) пересозданы штатным способом — через
  `_normalize_schema`/фикстуры самого файла, не руками (так требует их же
  докстринг) — с `sort_keys=True` для минимального, читаемого диффа.

**Написан и запущен `scripts/apply_direction_content.py`** — читает
`direction_content_review.json`, обновляет только
description/skills_needed/subjects_to_develop/first_steps по slug (имя/код/
professions не трогает — те принадлежат `seed_riasec_directions.py`).
Результат: **92/92 обновлено**, подтверждено SQL — все 4 поля заполнены у
всех 92 строк (было 0/92 у каждого поля). Живая проверка: собрал
`StudentCareer` через `build_riasec_careers()` напрямую — `try_now`
корректно берёт первый шаг, `first_steps` в ответе больше нет вообще.

191/191 полный набор тестов, `npm run typecheck`/`build` фронта — чисто.

## Оставшиеся 5 пунктов из my-deep-analysis.md — СДЕЛАНО (2026-08-13)

Пользователь спросил "что ещё осталось из тех проблем" — свёл в 6 пунктов,
пользователь согласился на все сразу:

1. **Резюме < 3 предложений**: fallback `_summary()` теперь 3 предложения
   (добавлено мостик-предложение к остальному отчёту, не филлер). Промпт
   требует минимум 3 у ВСЕХ возрастов явно, добавлен пункт в чек-лист.
   Новый validator-чек `_check_summary_sentence_count`
   (`summary_too_short`) считает предложения по `[.!?]` — раньше проверялась
   только длина в символах (мин. 10), не число предложений. Correction hint
   добавлен.
2. **Стиль мышления — единая карточка вместо двух** (главное изменение):
   `thinking_style_notes` теперь РОВНО одна карточка на 1-2 сигнала, не одна
   на каждый. `thinking_style_content.py` дополнен: `THINKING_STYLE_ADJ`
   (короткое прилагательное для title, middle/senior), `THINKING_STYLE_
   CUE_SHORT` (junior — поведенческое описание без ярлыков/карьерной
   рамки, TZ §4.1), `THINKING_STYLE_IMPACT` (middle/senior — "где это
   обычно проявляется", вроде примера пользователя про
   лидерство/предпринимательство, но БЕЗ конкретных профессий — это не
   career_narrative). Junior получает просто объединённое поведенческое
   предложение без абстрактных ярлыков и без карьерной рамки — пример
   пользователя ("такие люди становятся лидерами компаний") сам по себе
   нарушает TZ §4.1 для junior (career talk запрещён), поэтому impact-часть
   реализована только для middle/senior. Validator: `_check_thinking_style_
   count` переписан — 1 карточка, если есть хотя бы один сигнал (не по
   одной на каждый), плюс новая проверка, что карточка цитирует ВСЕ
   evidence_ids сразу (`thinking_style_incomplete`), а не только один из
   двух. Отдельный, больший бюджет длины (`_THINKING_STYLE_DESC_MAX_LEN`)
   — объединённая карточка законно длиннее одиночной. Промпт переписан.
   4 новых fallback-теста + 2 новых validator-теста.
3. **«Что тебя драйвит» → «Что тебя мотивирует»**: заголовок в fallback
   (`_motivation_narrative`, хоть и не показывается напрямую студенту — не
   используется в v2-ответе, только валидируется) и в `MotivationSection.
   tsx` (реальный видимый заголовок) — оба переименованы.
4. **Занятия junior — общие ярлыки без ресурсов**: НЕ трогал —
   `MI_ACTIVITIES` содержит только названия кружков ("кружок чтения" и
   т.д.), без ссылок/книг/видео. Осознанно не добавлял конкретные внешние
   ресурсы (ссылки/названия книг/курсов) — не из чего их взять без
   выдумывания, тот же принцип, что и с направлениями.
5. **Завершающее предложение под «Что можно попробовать»**: новое поле
   `exploration_note` на `_ResultResponseBase` (не только `MiResultResponse`
   — как и `exploration_activities`, присутствует у обоих веток union, но
   значим только для junior). **Со значением по умолчанию, не required** —
   специально, чтобы уже закэшированные junior-отчёты без этого поля
   продолжали десериализоваться (`ResultV2Adapter.validate_json` в
   `report_service.py` иначе упал бы на `ValidationError`, не пойманной
   существующей Redis-error-resilience). Фронт: `ExplorationActivitiesSection.
   tsx` принимает `note`, рендерит под списком; `ResultsPage.tsx` прокидывает
   `report.exploration_note`. `Profy-Frontend/docs/result-api-contract.md`
   не обновлял — эта секция не была явно описана там раньше (не входила в
   исходный контракт), можно дополнить отдельно если понадобится.
6. **Middle: одинаковое описание карточек одного типа** — новый баг,
   найденный при ответе на вопрос "что осталось" (не тот же, что чинили
   раньше). `_STRENGTH_CARD_EXPLANATIONS` (одна строка на source_type)
   заменён на `_STRENGTH_CARD_EXPLANATION_VARIANTS` (2-3 варианта на тип),
   циклически выбираемые по индексу внутри типа — детерминированно, не
   случайно. 2-3 карточки одного типа (например riasec_category) больше не
   получают дословно одинаковое объяснение.

Регрессия проверена на 3 новых/изменённых validator-правилах (сломал
внутри контейнера, убедился что новый тест ловит поломку, восстановил,
пересобрал) — в процессе обнаружил и закрыл реальный пробел: тест на
`summary_too_short` изначально не был написан, добавлен отдельно.
198/198 полный набор (было 191). `npm run typecheck`/`build` фронта —
чисто. Живая проверка: 3 fallback-сценария (junior/middle/senior) с
реалистичным evidence — валидны, читаются связно; 2 живых LLM-сценария
(middle/senior) — оба успешны (`is_ai=True`), middle потребовал 1
corrective retry (`motivation_ungrounded`+`strength_card_count`) и
исправился со второй попытки — подтверждает, что ужесточение правил не
сломало вчерашний фикс надёжности LLM-пути.

## Живой кейс пользователя (плоский профиль + артефакты) — СДЕЛАНО (2026-08-13)

Пользователь прошёл тест сам и прислал реальный результат: strength_cards
дублировали "программирование/IT/робототехника" 3 раза, а профессии —
Архивариус/Аудитор/Бухгалтер (CSE), никак не связанные с этим интересом.
Подтверждено по БД (`assessment_id=29eab8d6-...`): `differentiation=11.5`
(плоский профиль, порог 25), `code=["C","E","R"]`, 3 артефакта
("Программирование"/hobby, "IT/программирование"/club, "Робототехника"/
hobby).

**Причина 1**: `_artifact_evidence()` в `report_narrative_context.py`
строила один EvidenceItem на каждый артефакт без объединения — разные
source_id с почти одинаковым текстом это НЕ то же самое, что дубли одного
evidence_id (это чинили раньше сегодня). Исправлено: `_group_similar_
artifacts()` — группировка по общим значимым словам (простая эвристика,
не ML) перед созданием evidence. "Программирование"/"IT/программирование"
(общее слово "программирование") объединяются в один EvidenceItem через
"; "; "Робототехника" не пересекается ни с одним словом и остаётся
отдельно. Промпт дополнен инструкцией: если текст evidence содержит ";"
— это уже объединённые упоминания, описывать одним наблюдением.

**Причина 2**: `career_match_score` (`riasec_service.py`) считает только
по топ-3 RIASEC-буквам — никогда не смотрит на subjects/artifacts. На
плоском профиле топ-3 фактически шум (разница между 3-м и 4-м местом —
доли балла), а карьеры всё равно подаются уверенно. Это архитектурная
проблема (§3 вариант B/C в `result-quality-fixes.md`) — полностью не
решена (это отдельная задача по пересмотру методологии), но добавлена
честная **вариант D**: когда `is_flat_profile=True` И есть хотя бы один
artifact-факт, `report_v2_assembler.assemble_result_v2()` добавляет к
summary отдельное предложение, объясняющее ограничение теста при близких
баллах и рекомendующее присмотреться и к направлениям, связанным с
увлечениями из профиля. Работает одинаково для LLM и fallback путей
(применяется post-hoc в assembler, не в narrative-пайплайне). Никогда не
показывается junior (там нет карьер вообще).

7 новых тестов (`test_report_narrative_context.py` — 3,
`test_report_v2_assembler.py` — 4), regression-proofed (сломал обе новые
проверки внутри контейнера по отдельности, оба раза новые тесты поймали
поломку, восстановил). 205/205 полный набор (было 198). **Живая проверка
на РЕАЛЬНЫХ данных этого пользователя** (те же артефакты, тот же RIASEC-
профиль, реальный LLM-вызов): artifact-evidence корректно объединился в 2
записи вместо 3, strength_cards — 5 разных карточек без повтора, summary
получил честную пометку про увлечения. LLM потребовал 1 corrective retry
(`motivation_ungrounded`) — сработал штатно, подтверждает, что вчерашний
фикс надёжности не пострадал.

## Онбординг-данные забивали "Сильные стороны" — СДЕЛАНО (2026-08-13)

Пользователь уточнил, что предыдущий фикс (объединение похожих артефактов
+ честная пометка) не решал главное: strength_cards должны в первую
очередь показывать то, что нашёл САМ ТЕСТ (RIASEC + BigFive), а не то, что
пользователь сам о себе написал при онбординге — иначе получается ровно то,
что он увидел живьём: "программирование" в сильных сторонах рядом с
предложенной профессией "бухгалтер", которые никак не связаны, и читателю
кажется, что приложение не понимает само себя.

**Причина**: `build_report_narrative_context()` добавляла evidence в
порядке riasec/personality/motivation/thinking_style → onboarding
(subjects_liked/subjects_easy/artifacts), но БЕЗ ограничения на онбординг
— если тестовых фактов мало (например, только 1 riasec + 2 личностных),
а онбординг-данных много (3 артефакта), онбординг-данные заполняли
оставшиеся слоты почти без ограничений и визуально доминировали.

**Исправлено**: `ONBOARDING_SOURCE_TYPES = frozenset({"subject_liked",
"subject_easy", "artifact"})` и `_MAX_ONBOARDING_STRENGTH_EVIDENCE = 2` —
онбординг-факты (все три типа вместе) обрезаются до 2 ДО того, как попадают
в общий evidence — тестовые факты (riasec_category/personality) никогда не
обрезаются. Плюс — карточки, построенные на онбординг-evidence, теперь
явно помечены как "не из теста", с формулировкой "можно развивать
параллельно" (и в fallback, и в промпте для LLM) — это то самое требование
пользователя: "программирование — его сильная сторона, которую он может
развивать параллельно". Поскольку riasec_category evidence — это именно
то, что связывает strength_cards с объяснением "почему тебе подходит эта
профессия" в карточках направлений (`_matched_strengths_for` в
`report_v2_assembler.py`), приоритет тестовых фактов автоматически делает
"Сильные стороны" согласованными с предложенными профессиями — без
переделки самого алгоритма подбора (§3 вариант B/C по-прежнему открыт).

3 новых теста, regression-proofed. 207/207 полный набор (было 205). **Живая
проверка на тех же реальных данных, что и в прошлый раз** (тот же
пользователь, те же артефакты, реальный LLM-вызов): было 6 карточек, из
них 3 про программирование/IT/робототехнику (50%) — стало 5 карточек, из
них 4 явно из теста (RIASEC: организованность, работа руками, лидерство,
порядок) и ровно 1 про программирование с явной пометкой "это не из
теста... отдельный, самостоятельный интерес". LLM потребовал 1 corrective
retry, отработал штатно.

## Продуктовое решение: RIASEC остаётся единственным источником для карьер (2026-08-13)

Пользователь закрыл §3 вариант B/C насовсем: RIASEC — единственный
источник для подбора профессий, сознательно (научная обоснованность,
авторитетность теста нельзя размывать). Onboarding-данные (артефакты/
предметы) не для карьерного матчинга — их роль: общая картина пользователя
и что ему можно/нужно развивать (кружки/секции). Сегодняшние варианты D/E
(честная пометка + приоритет тестовых фактов в strength_cards) — это и
есть финальное решение для этой темы, не промежуточный шаг.

Всплыла идея отдельной секции «Что развивать / куда сходить» для
middle/senior на основе onboarding-артефактов, независимая от RIASEC
(у junior есть `exploration_activities`, но это MI-тест, не onboarding).
**Пользователь явно попросил пока ничего не строить** — зафиксировано как
контекст для будущего запроса, не задача.

## Университеты: не залиты, дублирующий скрипт удалён (2026-08-13)

Пользователь спросил «куда пропали университеты» — разобрался: ничего не
пропадало и не терялось. Провёл git-археологию по всем веткам/коммитам
(`origin/dev`, `New-Test-Logic`, стэши) в поисках «старой работы по
специальностям вузов» — нашёл отдельную, никогда не сливавшуюся систему
"Akinator" (AKN-002…009, belief-walk движок, 56 специальностей без
Holland-кодов) на `origin/dev`, но подтвердил: это не то же самое, что
искал пользователь, и никогда не было объединено с RIASEC-системой.

Реальная причина оказалась проще: `scripts/seed_kz_universities.py`
(55 вузов Алматы+Астаны, ~739 программ, из `university-data/*.py` +
`scripts/specialty_profession_map.py`) физически существовал и был
корректно написан, но **ни разу не вызывался** ни в `start.sh`, ни
где-либо ещё — в БД было только 12 вузов от отдельного, более старого
`scripts/seed_universities.py`.

Также проверил (по прямому запросу пользователя) — не сироты ли профессии
в `directions` относительно реальных вузовских специальностей: **0 сирот
из 92** — каждая профессия (включая «Биржевой брокер», которая казалась
подозрительной) имеет минимум одну реальную специальность в
`specialty_profession_map.py`. Каталог профессий трогать не пришлось.

**Сделано**:
1. Запущен `seed_kz_universities.py` — 55 вузов (43 новых + 12
   переиспользованных по `LEGACY_NAME_BY_SLUG`), 739 программ.
2. Найдено и удалено 16 «богатых» Program-записей от старого
   `seed_universities.py` (min_gpa/ЕНТ/IELTS/эссе), дублирующих логику —
   по явному решению пользователя удалить их вместе с файлом, несмотря на
   потерю детальности (`roadmap_builder.py` уже терпимо обрабатывает
   отсутствие этих полей — задокументировано в его собственном коде).
3. Удалён файл `scripts/seed_universities.py` целиком.
4. `start.sh` исправлен: убран вызов удалённого скрипта, добавлен вызов
   `seed_kz_universities.py`.
5. Обновлены комментарии в `roadmap_builder.py` и
   `test_university_requirements_mapping.py`, ссылавшиеся на удалённый
   файл.

207/207 тестов зелёные. Живая проверка: `search_programs()` по slug'у
`razrabotchik-programmnogo-obespecheniya` возвращает 10 реальных программ
из реальных вузов (Al-Farabi KazNU и др.).

**Итог по всей цепочке за 2026-08-13**: изначальная жалоба пользователя
"результат неинтересный, читается глупо" — от диагностики (LLM почти
никогда не проходил валидацию → contentless fallback) через content-shape
баги (дубли, перепутанные title/description) до сегодняшнего структурного
разрыва (карьеры не связаны с остальными фактами + 0/92 направлений без
контента) — все найденные и согласованные с пользователем пункты закрыты
или явно задокументированы как отдельная будущая задача (§3 вариант
B/C — пересмотр карьерного матчинга; полное удаление inquiry-бэкенда —
ждёт редизайна roadmap).
