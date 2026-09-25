# Big Five retired from the active test pool

Big Five (IPIP-NEO-120) больше не задаётся новым прохождениям теста — ни для
junior, ни для middle, ни для senior. Уже пройденные тесты с Big Five
остаются доступны для просмотра в админке без изменений.

## Что изменилось для новых прохождений

- Вопросы Big Five больше не приходят в `GET /questions` ни для одного
  возрастного уровня (`app/services/question_service.py::get_all_questions`).
- У junior вся фаза парных вопросов (forced-choice) убрана целиком —
  `GET /{assessment_id}/pairs` теперь всегда возвращает `[]` для junior
  (`app/services/question_pair_service.py::get_pairs`). Она целиком состояла
  из Big Five; замены не предусмотрено, junior-тест теперь чисто Likert по MI.
- У middle пары остаются (RIASEC-дилеммы), но Big Five-пары больше не
  отдаются.
- Прохождение теста больше не требует ответов на Big Five для завершения
  (`app/services/assessment_shared.py::likert_total_questions` больше не
  считает Big Five в знаменателе).
- Отчёт (`/result/generate`) для нового прохождения не содержит блоков «Твой
  характер» (personality) и «Стиль мышления» (thinking style) — секции
  полностью отсутствуют (`personality_notes: []`, `personality_note: ""`,
  `thinking_style_notes: []`), а не placeholder с текстом.

## Что НЕ изменилось (инвариант)

Content pipeline этого репозитория устроен так, что self-healing
seed-скрипт (`scripts/seed_bigfive_questions.py`) удаляет из БД любую
строку `Question`, которой нет в bank-файле (`scripts/bigfive_question_bank.py`),
а `user_responses.question_id` имеет `ForeignKey(..., ondelete="CASCADE")`.
Поэтому:

- **`scripts/bigfive_question_bank.py` не тронут.** Ни одного вопроса из
  банка не убрано.
- **`scripts/seed_bigfive_questions.py` остаётся в CD-пайплайне** как есть
  (между `seed_riasec_questions.py` и `seed_mi_questions.py` в
  `.github/workflows/cd.yml`/`cd-dev.yml`). Раз банк не меняется, скрипт
  навсегда остаётся no-op ресинком — его orphan-delete-логика (строки 77-80)
  никогда не сработает.
- **`scripts/seed_question_pairs.py`/`scripts/question_pairing.py`** тоже не
  тронуты — Big Five `QuestionPair`-строки продолжают существовать в БД,
  просто больше не выбираются `get_pairs`.
- **Ни одна строка `Question`/`QuestionPair` не удаляется** нигде в этом
  изменении — весь эффект достигается добавлением `WHERE`-условий в
  read-path-сервисах.
- **Postgres enum `question_instrument_enum`** (`riasec`/`big_five`/`mi`,
  `alembic/versions/0025_add_bigfive_instrument.py`) не тронут — никаких
  Alembic-миграций, значение `big_five` остаётся валидным навсегда.

Исключение сделано на уровне query-фильтров, а не контента — по аналогии с
уже существующим паттерном исключения RIASEC для junior в
`question_service.py` (junior перешёл на MI, но старые RIASEC-строки
остались в БД и просто не выбираются).

## Механизм: `RETIRED_INSTRUMENTS`

`app/services/age_tiers.py`:

```python
RETIRED_INSTRUMENTS: frozenset[QuestionInstrument] = frozenset({QuestionInstrument.big_five})
```

Подключён в:

- `app/services/question_service.py::get_all_questions` — `Question.instrument.not_in(RETIRED_INSTRUMENTS)`, для всех возрастных уровней.
- `app/services/assessment_shared.py::likert_total_questions` — то же самое, знаменатель гейта завершения теста.
- `app/services/question_pair_service.py::get_pairs`:
  - junior — короткое замыкание `return []` в начале функции (явно, а не через фильтр до нуля).
  - остальные (middle) — `QuestionPair.instrument.not_in(RETIRED_INSTRUMENTS)`.

`app/services/bigfive_service.py` **сознательно не фильтруется** этой
константой — его `question_counts`/`facet_counts` должны честно считать
исторический банк Big Five, потому что эти функции используются в гейте
`compute_bigfive` (см. ниже) для скоринга старых/переходных прохождений.

## Механизм: гейт `compute_bigfive`

Наивное «просто перестать отвечать» не подходит: `bigfive_service.normalize()`
при нулевых ответах не возвращает «пусто», а возвращает мусор — 0% по
Openness/Conscientiousness/Extraversion/Agreeableness и **фиктивные 100%**
Emotional Stability (`emotional_stability = 100 - N`, а N при нулевых
ответах нормализуется в 0).

Поэтому в `app/services/report_service.py::build_report` добавлен явный
гейт перед расчётом Big Five/thinking style/personality:

```python
bf_counts = await bigfive_service.question_counts(db, age_group)
bf_total = sum(bf_counts.values())
bf_answered = await bigfive_service.answered_count(assessment_id, db)
compute_bigfive = bf_total > 0 and bf_answered >= bf_total
```

Гейт — «полностью отвечено», а не «хоть что-то отвечено»: единственный
сценарий, когда `bf_answered > 0` у прохождения без старого
`AnalysisResult`, — пользователь, застигнутый деплоем посреди теста
(успел ответить на часть Big Five до раскатки фильтра). Частичный ответ
даёт тот же эффект «мусорных» цифр, что и полное отсутствие — поэтому
профиль считается только при полном ответе, иначе не считается вовсе.

`bigfive_service.answered_count(assessment_id, db)` — новая функция,
считает реальные `UserResponse` на Big Five для конкретного прохождения
(без ограничения по `age_tier`, чтобы поймать переходный кейс независимо
от того, какого уровня вопрос был отвечен).

## Изменения в схемах

- `app/schemas/result_v2.py::_ResultResponseBase.personality_notes` — было
  `Field(min_length=5, max_length=5)` (обязательное поле), стало
  `Field(default_factory=list)` + валидатор, допускающий ровно 0 или ровно 5
  элементов (не произвольную длину). Версия `report_version`/ключ кеша
  (`report:v3`) **не бампались** — старые закэшированные ответы (5
  элементов) валидны и дальше, а новый `assessment_id` физически не может
  иметь старый кеш.
- `app/schemas/admin_result.py::AdminThinkingStyle` — 4 обязательных
  `float`-поля без дефолтов получили `= 0.0`. Без этой правки
  `GET /admin/.../assessments/{id}` падал бы с `ValidationError` на любом
  новом прохождении (`thinking_style == {}`).
- `app/services/report_v2_assembler.py::build_personality_notes`/
  `build_personality_note` — добавлены ранние `return []`/`return ""` при
  пустом `personality_profile`. Раньше `build_personality_notes` падал с
  `KeyError` (список из 5 трейтов был захардкожен независимо от входа), а
  `build_personality_note` при пустом профиле возвращал текст
  «сбалансированно», утверждая наличие данных, которых нет.

## Требуется координация с фронтом

Секции «Твой характер»/«Stil мышления» теперь могут легитимно быть пустыми
(`personality_notes: []`, `thinking_style_notes: []`) для нового отчёта.
Нужно подтвердить, что фронт скрывает эти блоки при пустом списке (как уже
делает для `exploration_activities`/`careers` в других ветках), а не
рендерит пустую рамку.

## Проверка

Автоматические тесты (все проходят на реальной посеянной dev-БД —
`docker compose exec api pytest`, 506 passed):

- `tests/integration/test_big_five_retired_from_active_pool.py` — новый
  файл: Big Five не отдаётся ни одному возрастному уровню; junior-пары
  всегда `[]`; middle сохраняет RIASEC-пары, теряет Big Five;
  Big Five-строки остаются в БД; знаменатель гейта завершения совпадает с
  фактически отданными вопросами.
- `tests/integration/test_report_completion_gate.py` — три новых теста:
  свежий отчёт без ответов на Big Five даёт пустые секции; частичный ответ
  (переходный кейс) тоже даёт пустые секции; полный ответ на реальный банк
  уровня даёт полные 5 карточек (легаси-эквивалентный путь).
- `tests/unit/test_report_v2_assembler.py` — регрессионные пины на
  `build_personality_notes([]) == []` / `build_personality_note({}) == ""`.
- `tests/unit/test_admin_result_schema.py` — регрессионный пин на
  `AdminAnalysisResultResponse.model_validate` с пустым `thinking_style`.
- `tests/unit/test_result_v2_schema.py` — `personality_notes` валиден и при
  0, и при 5 элементах, невалиден при любом другом количестве.
- `tests/snapshots/openapi_mi_result_response.json` /
  `openapi_riasec_result_response.json` — обновлены под новую (необязательную)
  форму `personality_notes`.
- `tests/integration/test_report_cache_resilience.py` — тест устаревшего
  кешированного payload переключён с `personality_notes` (больше не
  обязательное поле, значит не годится как пример) на `thinking_style_notes`.
- `tests/integration/test_age_matrix_full_flow.py` — не потребовал
  изменений: его хелпер `_seed_bigfive_minimal` полностью отвечает на
  посеянные Big Five вопросы через реальные submission-пути, поэтому
  проходит через ветку `compute_bigfive=True` как легаси-эквивалентный
  случай.

Ручная проверка (рекомендуется перед проды): для каждого возрастного
уровня пройти тест целиком через API, убедиться что вопросов/пар Big Five
не показывается, отчёт генерируется без ошибок с пустыми personality/
thinking style секциями; отдельно найти/засеять одно старое прохождение с
реальными Big Five данными и убедиться, что `GET /admin/users/{id}` и
`GET /admin/assessments/{id}` показывают его без изменений.
