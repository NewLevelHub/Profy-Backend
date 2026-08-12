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
  проверку для остальных языков, а не проверяет их).

Это и есть содержание оставшихся RS-тикетов.
