# Контракт локализации Profy (ru + kk)

Единый источник правды по локализации для бэкенда и фронтенда. Все тикеты эпика
`ProfOr/Тикеты-локализация-KZ/` ссылаются на этот документ, а не дублируют
решения. Если код и этот документ расходятся — чинится расхождение (обычно
обновляется документ, но решение принимается явно).

Статус: **в работе**. `kk` ещё не включён для пользователей — см. «Выкатка».

---

## 1. Поддерживаемые локали

- `ru` — язык по умолчанию.
- `kk` — казахский.
- Формат кода — BCP-47 short (двухбуквенный). В БД и API — строго строки `ru` / `kk`.
- В Postgres выбор языка хранится через enum-тип `locale_enum` (значения `ru`, `kk`).
- Английский и прочие языки — вне scope, но вся инфраструктура строится расширяемой
  (`locale` — код языка, а не булев флаг `is_kazakh`).

## 2. Выкатка (без feature-flag)

Флага `KZ_LOCALE_ENABLED` **нет**. Вместо него `kk` физически отсутствует в
списке поддерживаемых локалей на протяжении всей разработки:

- бэкенд: `app/i18n.py` → `SUPPORTED_LOCALES = ("ru",)` (комментарий
  `# KZ-603 добавляет "kk"`);
- фронтенд: `src/shared/i18n/index.ts` → `supportedLngs: ['ru']` (тот же комментарий).

Пока `kk` не в этих списках:
- `normalize_locale("kk")` возвращает `ru` — партиально готовый перевод недостижим
  для пользователя;
- компонент `LanguageSwitcher` рендерит `null` (при ≤ 1 реальной локали).

Финальный тикет **KZ-603** одним маленьким PR добавляет `kk` в оба места (и этим
же делает переключатель видимым). Мержится последним — после зелёных KZ-601
(E2E) и KZ-602 (CI-гарды). Откат = `revert` этого PR.

**Следствие — порядок мержа обязателен.** Любой тикет эпика не должен менять
поведение для `ru`-пользователя до KZ-603. Всё пишется как «`kk` рядом с `ru`»,
никогда «вместо». Полный порядок — в `00-ЭПИК-локализация-KZ.md`, раздел
«Порядок мержа».

## 3. Разрешение локали запроса

Порядок (первое непустое выигрывает):

1. `users.locale` — если запрос аутентифицирован и поле задано (не дефолт).
2. Заголовок `Accept-Language` (первое значение из `SUPPORTED_LOCALES` с учётом
   q-весов).
3. `ru` (дефолт).

Для анонимных запросов (регистрация, вход, сброс пароля, подтверждение почты)
работает только шаг 2 — `users` ещё нет или он не в контексте.

Реализация — `app/i18n.py` (`normalize_locale`, `ContextVar current_locale`,
`get_locale()`) + FastAPI middleware, уточняемый зависимостью `get_current_user`
(user.locale перезаписывает локаль из заголовка). Детали — тикет KZ-102.

Сервисы читают локаль через `get_locale()`, не через `Request`. Фоновые задачи
(генерация отчёта/роадмапа вне HTTP-контекста) получают локаль явным аргументом
из `users.locale` владельца артефакта.

## 4. Как фронт сообщает локаль

- Заголовок `Accept-Language: <loc>` на **каждом** запросе `apiClient`
  (`src/shared/api/client.ts`, интерцептор запроса) — значение из локаль-стора.
- Залогиненный пользователь дополнительно хранит выбор на сервере: `users.locale`,
  меняется через `PATCH /api/v1/auth/me { "locale": "ru" | "kk" }` при
  переключении языка.
- Явный query-параметр `?lang=` не вводим.

## 5. Политика фолбэка

- Нет `kk`-перевода строки / поля → отдаём `ru`-версию.
- **Никогда** не отдаём ключ перевода, `null` или пустую строку туда, где ждётся
  текст.
- Каждый фолбэк инкрементит метрику `i18n.fallback{locale, area}` (бэк — из
  хелпера `pick_locale`; фронт — из `saveMissing` i18next). Аналитика — тикет KZ-604.
- Если в `{locale: text}` нет ни запрошенной локали, ни `ru` (или маппинг пуст /
  `None`) — `pick_locale` **поднимает `MissingLocalizedText`** (после инкремента
  метрики), а не возвращает `""`: `ru` — источник правды, банки self-heal, так что
  это баг данных, который должен падать в тестах/CI, а не тихо рендерить пустоту.

## 6. `profiles.language` — это НЕ UI-локаль

`profiles.language` — свободная строка «язык обучения» ученика. Используется как:
- сигнал подбора программ (сопоставление с `Program.language`);
- хинт для LLM (`StudentContext.language`).

UI-локаль — отдельное поле `users.locale`. Связь только одна: при создании
профиля, **если пользователь ни разу не менял локаль явно** (`users.locale_explicit
= false`), она предзаполняется эвристикой из `profiles.language`:

```
значение матчит /казах|kazakh|qaz|қаз/i  →  users.locale = "kk"
иначе                                     →  users.locale = "ru"
```

Только полные корни (`казах`, `kazakh`) и script-специфичные `qaz`/`қаз` — голый
`kaz`/`каз` даёт ложные срабатывания на обычных словах («показать», «рассказать»).

Любой явный выбор через переключатель ставит `users.locale_explicit = true` и
навсегда отключает это предзаполнение для пользователя. Переопределить
переключателем можно в любой момент.

## 7. Ошибки и `detail=` в роутерах

- Бэкенд возвращает стабильный машинный `error_code` в теле ошибки + оставляет
  человекочитаемый `detail` на русском (обратная совместимость с текущими
  потребителями).
- Локализованный текст ошибки собирает фронт из словаря по `error_code`.
- Новые ошибки обязаны иметь `error_code`.

### KZ-309 — реализовано

- `app/errors.py::AppError(HTTPException)` несёт `error_code`; хендлер
  `app_error_handler` в `app/main.py` рендерит тело
  `{"detail": "<ru>", "error_code": "<code>"}`. Обычный `HTTPException` не
  затронут (`{"detail": …}` как прежде).
- На `AppError` переведены **только** пользовательские русские `detail=` — 16
  мест в `assessment_service` / `direction_inquiry_service` / `goal_overlay_service`
  / `report_service` / `roadmap_builder` (13 уникальных кодов). `detail`-строки
  байт-в-байт прежние.
- Английские `detail=` (`"Profile not found"`, `"Access denied"`, `str(exc)`,
  auth-сентинелы …) — не локализуемая копия, оставлены как есть.
- Полный аудит-список + коды для фронтового словаря (KZ-203):
  `ProfOr/Тикеты-локализация-KZ/KZ-309-аудит-detail.md`.
- Тест: `tests/integration/test_error_locale.py`.

## 8. Хранение локализованного контента (вариант A: колонка `locale`)

Контент из Python-«банков» (`scripts/*_bank.py`) — источник правды; `seed_*.py`
делают full-resync с удалением строк не из банка (см. `CLAUDE.md`). Поэтому
казахские версии живут в банках и попадают в БД через seed, не правкой БД.

Модель хранения — **вариант A**:

- В таблицах `questions`, `question_pairs`, `motivation_statements`,
  `motivation_pairs`, `directions` добавляется колонка `locale`
  (`locale_enum`, `NOT NULL`, `server_default 'ru'`).
- Уникальность строки — составной ключ `(<natural_key>, locale)`, где
  `<natural_key>` — существующий стабильный ключ строки в её банке.
- Одна логическая единица контента = до N физических строк (по одной на локаль).
- Структурные поля (`order`, `age_tier`, `riasec_type`, `bigfive_domain`,
  `keyed`, `facet`, `mi_category`, `holland_code`, `slug` …) **обязаны совпадать**
  между локалями одной единицы.
- Формат записи в банке:
  `{"key": "...", "text": {"ru": "...", "kk": "..."}, ...структурные поля...}`.
- `seed_*.py` full-resync: «ключ строки» = `(natural_key, locale)`; удаляет только
  `(key, locale)`, которых нет в банке для этой локали; строки других локалей не
  трогает.
- Чтение — через хелпер `app/i18n.py::pick_locale(mapping, locale)` (фолбэк на
  `ru` + инкремент `i18n.fallback`).

### `<natural_key>` по банкам

| Банк / таблица | Натуральный ключ | Локализуемые поля | Структурные (общие для локалей) |
|---|---|---|---|
| `riasec_question_bank` → `questions` | `order` (позиционный, 1..N) | `text`, `short_text` | `riasec_type`, `age_tier`, `icon`, `order` |
| `bigfive_question_bank` → `questions` | `order` | `text` | `bigfive_domain`, `facet`, `keyed`, `age_tier`, `order` |
| `mi_question_bank` → `questions` | `order` | `text`, `short_text` | `mi_category`, `age_tier`, `icon`, `order` |
| `motivation_statement_bank` → `motivation_statements` | `code` | `text` | `category`, `code` |
| `motivation_pair_bank` → `motivation_pairs` | `(code, side)` / порядковый | `text` (обеих сторон) | `category`, `intensity`, порядок |
| `riasec_professions` → `directions` | `title` (дедуп по первому вхождению) | `title`?, `description`, `professions`, `skills_needed`, `subjects_to_develop`, `first_steps` | `slug`, `holland_code`, `section` |

> `title` направления — одновременно натуральный ключ и отображаемое имя. Для `kk`
> имя переводится, но **`slug` не меняется** — сопоставление локалей идёт по `slug`
> (или по `holland_code`+позиции до появления slug). Детали — KZ-306.

### Формат банка «до / после» (пример — RIASEC-вопрос)

```python
# ДО (сейчас):
{"riasec_type": "R",
 "text": "Мне нравится решать практические, приземлённые задачи",
 "short_text": "Чинить и мастерить", "icon": "🔧"}
# order / age_tier дописываются постобработкой в конце файла банка.

# ПОСЛЕ (KZ-301): локализуемые поля — {locale: str}, структурные не трогаем.
{"riasec_type": "R",
 "text": {
     "ru": "Мне нравится решать практические, приземлённые задачи",
     "kk": "Практикалық, нақты міндеттерді шешкенді ұнатамын",
 },
 "short_text": {"ru": "Чинить и мастерить", "kk": "Жөндеп, құрастыру"},
 "icon": "🔧"}
```

Пример — профессия (`riasec_professions`):

```python
# ДО:
{"section": "Realistic", "title": "Инженер-механик", "holland_code": "RIS"}

# ПОСЛЕ:
{"section": "Realistic", "holland_code": "RIS",
 "title": {"ru": "Инженер-механик", "kk": "Механик-инженер"}}
# slug вычисляется из title["ru"] (стабильный якорь) — см. KZ-306.
```

### Поведение `seed_*.py` full-resync с измерением `locale`

- «Ключ строки» = `(<natural_key>, locale)`.
- Для каждой `(key, ru)` из банка — upsert `ru`-строки (как сейчас).
- Для каждой `(key, kk)`, где в банке есть непустой `text["kk"]` — upsert `kk`-строки
  с теми же структурными полями, что у `ru`-близнеца.
- Delete: удаляются только `(key, locale)`, которых нет в банке **для этой локали**.
  `ru`-строки не трогаются отсутствием `kk`-перевода и наоборот.
- Инвариант-проверки банка вида `assert len(QUESTIONS) == 146` останутся про
  логические единицы (по `ru`), не про суммарное число строк в БД.

Детали миграций и правок seed-скриптов — тикет KZ-301.

### Реализация KZ-301 (что уже в коде)

- Миграция `f3b9c1d47a20` — колонка `locale` (`locale_enum NOT NULL DEFAULT 'ru'`)
  + индекс `ix_<table>_locale` на всех пяти таблицах. Существующие строки → `ru`.
- Составной **DB-UNIQUE `(<natural_key>, locale)`** заведён только там, где раньше
  был одиночный DB-UNIQUE по ключу: `directions` (`uq_directions_slug_locale`,
  бывший `ix_directions_slug`) и `motivation_pairs`
  (`uq_motivation_pairs_pair_index_locale`, бывший `ix_motivation_pairs_pair_index`);
  бывшие уникальные индексы понижены до обычных lookup-индексов. У `questions`,
  `question_pairs`, `motivation_statements` DB-уникальности по натуральному ключу
  не было — seed по-прежнему дедуплицирует по `(natural_key, locale)` в Python,
  а нового DB-UNIQUE нет (иначе он бы впервые запрещал фикстуры с «неважным»
  `order=0`).
- Формат банка: локализуемые поля — `{locale: str}` (`text`, `short_text`, …),
  структурные — как есть; банк экспортирует `LOCALES` со списком своих локалей.
  На KZ-301 все банки ещё плоские `ru`-строки; **KZ-302** переводит
  `riasec_question_bank.py` (см. ниже), KZ-303…306 — остальные. Каждый
  ещё-не-тронутый `seed_*.py` объявляет `BANK_LOCALE = "ru"` и трогает только
  `locale='ru'` строки; переведённый seed итерирует `LOCALES`, скоуп резинка —
  по каждой локали отдельно (`(order, locale)` не из банка для этой локали →
  удаляется; строки других локалей целы).
- Чтение per-locale строк — хелпер `app/services/content_locale.py::localized_rows`
  (не `pick_locale`, который для `{locale: text}`-маппингов на JSON-полях).
  Фолбэк **по каждой логической единице (natural key)**: строка запрошенной
  локали побеждает, где её нет — берётся `ru` и пишется `record_fallback`.
  Порядок результата — по `ru`-набору (канонический), переведённые строки
  подставляются на место. Так частично переведённый банк отдаёт «переводы +
  `ru` на остальное», а не короткий набор — тикеты KZ-302…306 не обязаны
  мержиться вместе. Скоринговые знаменатели
  (`riasec/bigfive/mi_service.question_counts` и его keying-варианты,
  `assessment_shared.likert_total_questions`, `motivation*_service.total_*`,
  2 счётчика в `admin_service`) прибиты к `ru` напрямую — `ru` всегда полный
  канонический набор, счёт не зависит от локали UI. Запросы, доходящие до
  контент-таблицы только через join `user_responses`, локаль-фильтра не требуют.

### KZ-302 — банк RIASEC-вопросов (kk)

- `scripts/riasec_question_bank.py`: список `QUESTIONS` не тронут (чистый
  `ru`-дифф, git-blame цел); переводы — в `_KK_TEXT` / `_KK_SHORT`, ключ = точная
  `ru`-строка (реордер-безопасно). Пост-обработка сворачивает поля в
  `{"ru": …, "kk": …}` и ассертит точное покрытие (нет пропусков/лишних ключей).
  `LOCALES = ("ru", "kk")`.
- `seed_riasec_questions.py` итерирует `LOCALES`; kk-строки клонируют
  `riasec_type` / `order` / `age_tier` / `icon` `ru`-близнеца. Идемпотентен
  (повторный прогон: `0` вставок/удалений).
- Перевод — LLM по глоссарию `Profy-Frontend/docs/i18n.md`; **вычитка носителем
  ещё не сделана** — чек-лист: `ProfOr/Тикеты-локализация-KZ/KZ-302-вычитка-kk.md`.
- Все 146 middle+senior (и junior) вопросов имеют `kk`; big_five / mi — ещё
  `ru`, поэтому `kk`-прохождение теста интересов отдаёт казахские RIASEC-строки
  и `ru` на big_five/mi (per-key фолбэк). Скоринг не изменился
  (`test_content_locale.py`, `test_age_matrix_full_flow.py`).

### KZ-303 — банк Big Five (kk)

- `scripts/bigfive_question_bank.py` — та же схема: `QUESTIONS` не тронут,
  `_KK_TEXT` (120) + `_KK_SHORT` (30) по `ru`-строке-ключу, свёртка в
  `{"ru": …, "kk": …}` + ассерт покрытия, `LOCALES = ("ru", "kk")`.
- `keyed` (plus/minus), `bigfive_domain`, `facet` — не тронуты; полярность
  `minus`-пунктов сохранена в казахской формулировке, поэтому
  `bigfive_service` и `thinking_style_service` дают тот же результат
  (`test_question_bank_has_a_complete_kk_set[big_five]`, `test_bigfive_service`,
  `test_age_matrix_full_flow`).
- `seed_bigfive_questions.py` итерирует `LOCALES`, идемпотентен. DB:
  big_five ru=120 + kk=120.
- **Вычитка носителем пока не сделана** —
  `ProfOr/Тикеты-локализация-KZ/KZ-303-вычитка-kk.md`.

### KZ-304 — банк MI (junior) + question-pairs (kk)

- `scripts/mi_question_bank.py` — та же схема (`_KK_TEXT` 48, `_KK_SHORT` 48,
  `LOCALES=("ru","kk")`, свёртка + ассерт покрытия). `mi_category` не тронут.
- `scripts/question_pairing.py` — `PAIRS` (67: 34 junior + 33 middle) не тронут
  по структуре; параллельные `_KK_*_CONTENT` (4 dict-а: junior/middle ×
  riasec/big_five) с теми же tuple-ключами хранят только текстовые поля.
  `_merge_bilingual()` сворачивает `frame` / `option_a_text` / `option_b_text`
  каждой записи в `{"ru": …, "kk": …}` (иконки — общие) и ассертит точное
  покрытие ключей + полей. `PAIR_LOCALES = ("ru", "kk")` экспортируется.
- `seed_mi_questions.py` итерирует `LOCALES`; `seed_question_pairs.py` итерирует
  `PAIR_LOCALES` — `order_to_id` резолвится **по каждой локали** (kk-пара
  ссылается на kk-строки вопросов), ключ `(instrument, pair_index, locale)`,
  резинк per-locale. Иконки одинаковы между локалями. Оба идемпотентны.
- DB: mi ru=48 + kk=48; question_pairs ru=67 + kk=67 (34 junior + 33 middle
  каждая); структурный паритет ru↔kk (age_tier, иконки) — 0 расхождений;
  kk-пары ссылаются на kk-`question_a_id`/`question_b_id`, не на ru.
- junior-флоу на `kk`: `question_pair_service.get_pairs` отдаёт kk `frame` +
  option-тексты; выбор пары пишется как 2 `UserResponse` на kk-`question_id` →
  riasec/bigfive-скоринг тот же (структурные поля вопроса идентичны).
  `test_content_locale.py::test_get_pairs_kk_serves_translated_frame_and_options`
  + `test_age_matrix_full_flow` (junior) зелёные.
- **Вычитка носителем пока не сделана** —
  `ProfOr/Тикеты-локализация-KZ/KZ-304-вычитка-kk.md`.

### KZ-305 — мотивационные утверждения + Harter-пары + лейблы ценностей (kk)

- `scripts/motivation_statement_bank.py` — `PHRASES` / `PHRASES_JUNIOR` не
  тронуты; позиционные копии `_KK_PHRASES` / `_KK_PHRASES_JUNIOR`
  (`dict[cat, list[4]]`, индекс N = kk от `PHRASES[cat][N]`) + ассерты
  покрытия. `STATEMENTS` loop сворачивает `text` **и** `text_junior` в
  `{"ru": …, "kk": …}`. `LOCALES=("ru","kk")`.
- `scripts/motivation_pair_bank.py` — `_CONTENT` не тронут; позиционная копия
  `_KK_CONTENT` (те же категории, 2 фасета, порядок `(positive, negative)`
  сохранён — конвенция a=+/b=− для скоринга не ломается). `PAIRS` сворачивает
  `text_a`/`text_b`. Harter-рамка kk: «Кейбір балалар …, ал басқалары …».
- `seed_motivation_statements.py` / `seed_motivation_pairs.py` итерируют
  `LOCALES`, резинк per-locale, идемпотентны. DB: statements ru=36 + kk=36,
  pairs ru=18 + kk=18; `category` совпадает ru↔kk (0 расхождений).
- `app/services/motivation_content.py` — добавлены `_MOTIVATION_LABELS_KK` /
  `_DRIVER_PHRASES_KK`; `highlight_phrases()` и новый `motivation_label()`
  резолвят `get_locale()` с фолбэком `ru` (student-facing driver-фразы отчёта
  теперь берут kk при `locale=kk`). Формальный перенос в `app/i18n/catalog/` —
  за KZ-307 (та же accessor-форма).
- **Вычитка носителем пока не сделана** —
  `ProfOr/Тикеты-локализация-KZ/KZ-305-вычитка-kk.md`.

### KZ-306 — каталог направлений/профессий (kk) — names + инфра

Сделано:
- `scripts/riasec_professions.py` — `PROFESSIONS` не тронут; `KK_NAMES`
  (145, ключ = точная `ru`-`title`) + ассерт покрытия; `LOCALES=("ru","kk")`.
  **`slug` и `holland_code` — НЕ per-locale**: slug всегда из `ru`-title
  (стабильный якорь), поэтому career-matching и `program_directions` (M2M по
  `direction.id`, линкует только `ru`-строки — 19362 линка, все `ru`) не
  затронуты.
- `seed_riasec_directions.py` итерирует `LOCALES`; `name` = `ru`-title либо
  `KK_NAMES[title]`; slug/holland_code общие; резинк per-locale. Идемпотентен.
  DB: directions ru=145 + kk=145.
- `apply_direction_content.py` — **locale-aware**: `direction_content_review.json`
  → `locale='ru'` строки, `direction_content_review_kk.json` (когда появится) →
  `locale='kk'`. Отсутствие kk-файла — не ошибка (печатает «skipped»), CD
  зелёный.
- `scripts/export_direction_glossary.py` (новый) → `scripts/data/direction_glossary_kk.json`
  = `[{slug, holland_code, name_ru, name_kk}]`, отсортировано по slug. **Это
  вход для KZ-401** (промпт/валидатор ИИ-генерации должен писать названия
  профессий ровно как в каталоге). Перегенерировать после правки имён/ре-сида.
- `direction_service` / `riasec_service.matched_careers` уже locale-aware
  (KZ-301); `test_content_locale.py::test_directions_kk_names_and_shared_slug`
  проверяет паритет + идентичность ранжирования matched_careers ru↔kk.

**Отложено в batch (решение пользователя):** `description` / `skills_needed` /
`subjects_to_develop` / `first_steps` для `kk` (≈ 1824 строки прозы) — наполнить
`scripts/direction_content_review_kk.json` тем же batch-прогоном, что и
описания вузов/программ (KZ-504). Инфраструктура (`apply_direction_content.py`,
per-locale строки) готова принять файл без изменений кода. До KZ-603 kk-описания
всё равно недостижимы (`get_locale()` не возвращает `kk`); `get_direction_by_slug`
под `kk` вернёт kk-строку с kk-именем и **пустым** description (fallback
`localized_rows` не сработает — kk-строка существует).
  - **Вычитка носителем (имена)** — `ProfOr/Тикеты-локализация-KZ/KZ-306-вычитка-kk.md`.

### KZ-307 — питон-литералы контент-сервисов → `app/i18n/catalog/`

- `app/i18n.py` стал пакетом `app/i18n/__init__.py` (импорты `from app.i18n import …`
  без изменений); добавлен подпакет **`app/i18n/catalog/`**. Каждый модуль-область
  = `RU` и `KK` деревья одинаковой формы; `catalog.tr(area)` резолвит по локали
  запроса с **пофайловым (по top-level ключу) фолбэком на `ru`** и инкрементом
  `i18n.fallback`. `catalog.key(area, *path)` — удобный индексер.
- Области: `riasec`, `bigfive`, `mi`, `motivation` (завершён перенос из KZ-305),
  `thinking_style`, `gap_analysis`, `university_requirements`, `resource_catalog`,
  `goal_overlay`.
- Сервисы `*_content.py` теперь — тонкие аксессоры-функции (`riasec_labels()`,
  `mi_activities()`, `personality_labels()`, `thinking_style_notes()`, …), а не
  модульные dict-константы. Все ~15 потребителей (`report_narrative*`,
  `report_v2_assembler`, `riasec_service`, `mi_service`, `direction_inquiry_service`,
  `admin_service`, `goal_overlay_service`, `gap_analysis_service`,
  `university_requirements`) переведены на вызовы функций. Тип возврата —
  дерево для текущей локали; **не кэшировать между запросами разной локали**.
- `gap_analysis_service` `comment=` → `catalog("gap_analysis")`; `_*_KEYS`/`_*_TERMS`
  остаются `ru` (match-data по бэкенд-данным, не UI — исключены из KZ-602-гарда,
  комментарий в файле). `resource_catalog`: `RESOURCE_CATALOG` → каталог (kind
  переведён, title — имя собственное, как названия вузов), `CATEGORY_KEYWORDS`
  остаётся `ru` (match-data). `goal_overlay_service`: единственная оставшаяся
  `ru`-строка — `raise HTTPException(detail=…)` (это KZ-309).
- Отчёт генерируется всё ещё `ru` (локаль в пайплайн — KZ-401); но аксессоры
  уже locale-aware, так что `_current_locale='kk'` → детерминированные части на
  казахском (`test_i18n_catalog.py::test_deterministic_report_pieces_follow_the_request_locale`).
- Тесты: `tests/unit/test_i18n_catalog.py` — форма RU↔KK, резолв по локали,
  пофайловый фолбэк + tally, explicit-locale override. Тест-файлы, тянувшие
  `_NOTES` / `RESOURCE_CATALOG` / `*_LABELS` напрямую, переведены на
  `app.i18n.catalog.<area>.RU` / аксессоры.
- **Вычитка носителем** — `ProfOr/Тикеты-локализация-KZ/KZ-307-вычитка-kk.md`.

### KZ-308 — письма верификации и сброса пароля (kk)

- Тема письма + plain-text тело → новая область каталога `app/i18n/catalog/email.py`
  (`RU`/`KK`, ключи `verification_subject` / `verification_plain` /
  `password_reset_subject` / `password_reset_plain`, единственный плейсхолдер
  `{code}`). HTML-тела — файлы: `verification.html` + `verification.kk.html`,
  `password_reset.html` + `password_reset.kk.html` (та же вёрстка, только текст,
  `lang="kk"`).
- `email_service.send_verification_email` / `send_password_reset_email` получили
  keyword-параметр `locale` (эти функции вызываются из best-effort шага после
  коммита, без request-контекста — явный параметр по правилу KZ-307).
  `_load_template(name, locale)` предпочитает `<stem>.<locale>.html`, падает на
  `ru`-файл если казахского нет (§5 — не отдаём пустое).
- **Локаль письма — выбор получателя, а не резолв запроса.** `_email_locale()`
  клампит по `KNOWN_LOCALES` (не `SUPPORTED_LOCALES`), т.е. `kk` работает до
  KZ-603: источник — `users.locale` (resend, сброс) либо `Accept-Language`
  регистрации, оба уже нормализованы через `KNOWN_LOCALES` на write-пути
  (`app/routers/auth.py`). Незнакомая/`None` локаль → `ru`.
- Вызовы: `auth_service.register` → `locale=locale` (из `Accept-Language`);
  `auth_service.resend_verification` и `password_reset_service.initiate_reset` →
  `locale=user.locale`.
- `ru`-письма — байт-в-байт как раньше (`tr("email", locale="ru")` отдаёт `RU`
  как есть; строки перенесены дословно).
- Тесты: `tests/integration/test_email_locale.py` — тема/тело/выбор шаблона по
  локали, `ru` без изменений, фолбэк незнакомой локали, регистрация с
  `Accept-Language: kk`, сброс по `users.locale`.
- **Вычитка носителем** — `ProfOr/Тикеты-локализация-KZ/KZ-308-вычитка-kk.md`.

### KZ-403 — детерминированные фолбэки отчёта (kk)

- **Область: только `/results`.** В проекте ИИ-генерация используется лишь для
  текста отчёта на `/results`; генерация роадмапов не используется, поэтому
  фолбэк-шаблоны в `roadmap_builder.py` НЕ трогали (см. AC ниже).
- `i18n.use_locale(locale)` — новый контекст-менеджер: форсирует
  `_current_locale` в обход `SUPPORTED_LOCALES` (клампит по `KNOWN_LOCALES`),
  восстанавливает при выходе. Нужен потому, что все аксессоры KZ-307
  (`mi_labels()`, `riasec_strength_phrases()`, `development_plan()` …) читают
  `get_locale()`, а `kk` до KZ-603 не проходит `set_locale()`.
- Строки детерминированного нарратива → `app/i18n/catalog/narrative_fallback.py`
  (`RU`/`KK`, ~34 листовых ключа; шаблоны с плейсхолдерами
  `{verb}`/`{adjectives}`/`{cues}`/`{impact}`/`{label}`/`{hint}`/`{name}`/`{clauses}`).
  `report_narrative_fallback.py` полностью параметризован по `locale`.
- Синтез-строки result_v2 (`build_interest_map_note`, `build_personality_note`,
  career-«why», flat-profile-примечание, `_join`) →
  `app/i18n/catalog/result_v2.py` (`RU`/`KK`, 11 ключей).
- `report_service.build_report` и `get_report`/`_shape_response` резолвят локаль
  **владельца артефакта** (`_resolve_owner_locale` → `users.locale`, не локаль
  читателя) и оборачивают весь проход scoring→текст→assemble в `use_locale`.
- `ru`-вывод байт-в-байт как раньше (`tr(area, locale="ru")` отдаёт `RU`;
  снапшот-тесты `test_fallback_narrative_locale.py::test_ru_output_is_unchanged_snapshot`,
  `test_report_v2_assembler.py`).
- Тесты: `tests/unit/test_fallback_narrative_locale.py` (валидность по
  построению для kk на 3 возрастах, отсутствие ru-доминантных полей, 5-6
  предложений в summary, все плейсхолдеры заполнены, ru-снапшот);
  `tests/integration/test_result_locale.py` (kk-владелец → казахский `/results`
  end-to-end, включая холодный кэш / reshape; ru не затронут).
- **Вычитка носителем** — `ProfOr/Тикеты-локализация-KZ/KZ-403-вычитка-kk.md`.
- Правки по ревью (2026-09-04):
  - `student_context.py` — локаль гейтится `SUPPORTED_LOCALES` (не `KNOWN_LOCALES`):
    единственные потребители — мёртвые roadmap/inquiry-промпт-билдеры без
    `use_locale`-обёртки, `kk` там дал бы полу-переведённый артефакт. Матчит
    `app/dependencies.py`.
  - `report_narrative_validator.py` — kk-ветки не только у `_check_language`:
    `BANNED_PHRASES_KK`, `JUNIOR_CAREER_TERMS_KK`, `_FRAME_PHRASE_SUBSTRINGS_KK`
    (проверяются вместе с `ru`-наборами при `language="kk"`). `_check_language_kk`
    step 1: перед Cyrillic-ratio вырезаются разрешённые латинские имена
    (`_ALLOWED_LATIN_TOKENS` — глоссарий `_locale`: Nazarbayev University,
    Data Engineer, DevOps…), чтобы валидный kk-текст с 2-3 именами собственными
    не ловил ложный `LANGUAGE_MISMATCH` → сожжённые ретраи → `ru`-фолбэк.
  - `report_narrative_service.py` — при `llm_client.is_enabled() == False`
    ранний `return` детерминированного нарратива **без** `record_fallback` и
    warning (LLM выключен — это штатный путь, не «фолбэк-инцидент»; алерты на
    долю validation-fallback больше не скачут от одного флага).

## 9. Хранение ИИ-артефактов — с ключом локали

**В проекте единственный живой ИИ-артефакт — нарратив отчёта на `/results`**
(роадмапы и direction inquiry — мёртвый код). Он персистится в `analysis_results`
и кэшируется в Redis **с привязкой к локали**: `ru` и `kk` не делят одну
строку/ключ.

### KZ-405 — реализовано

- `analysis_results.locale` (`locale_enum`, `NOT NULL`, `server_default 'ru'`);
  одиночный `UNIQUE(assessment_id)` → составной
  `UNIQUE(assessment_id, locale)` + обычный lookup-индекс. Миграция
  `a1c5e9d2b7f4`, обратима. Существующие строки → `'ru'`.
- Redis-ключ: `report_cache_key(assessment_id, locale)` →
  `report:v4:{locale}:{assessment_id}` (bump v3→v4). `report_cache_keys()` —
  список по всем `KNOWN_LOCALES`; retake / инвалидация чистят все локали.
- `report_service.build_report` / `get_report` резолвят локаль владельца
  (`_resolve_owner_locale`), строят ключ и `select(AnalysisResult).where(
  assessment_id==…, locale==loc)`; `INSERT` пишет `locale=locale`. Нет строки на
  нужной локали → `get_report` возвращает `None` (сигнал для KZ-406), **не**
  отдаёт чужую локаль. `retake` (`assessment_shared`) удаляет все локаль-строки.
- Остальные читатели `AnalysisResult` (админка ×3, gap-анализ, goal-overlay,
  мёртвые roadmap/inquiry) читают только локаль-инвариантные поля (баллы, коды) —
  детерминированно берут `ru`-строку: `.order_by((locale==ru).desc()).limit(1)`
  для `scalar_one*`, prefer-ru в bulk-словарях. Не падают на `MultipleResultsFound`.
- Детерминированные части (счёт тестов, топ-профессии, career-matching) между
  локалями идентичны — регенерируется только текст (`test_ai_artifact_locale_key.py`).
- Тест: `tests/integration/test_ai_artifact_locale_key.py`.

### KZ-406 — реализовано (backend + фронт-механизм)

- `GET /result/{id}` при отсутствии строки на локали владельца: `404` +
  `error_code="report_locale_not_generated"`, если отчёт есть на другой
  локали, иначе обычный `"Report not found"`. Роутер зовёт
  `report_service.resolve_report()` — 3-состояние (`OK` /
  `LOCALE_NOT_GENERATED` / `NOT_FOUND`) из **одного** запроса: на ассессмент
  ≤ `len(KNOWN_LOCALES)` строк, поэтому `select` без фильтра по локали стоит
  столько же, сколько прежний с фильтром, но заодно показывает, есть ли строка
  на другой локали — без второго near-duplicate `SELECT` на каждом ~2с поллинге.
- Ленивая регенерация уже работает через KZ-405: `POST /result/generate` →
  `build_report` создаёт строку на локали владельца, не трогая другую.
  `ru`-строка при переключении не удаляется (удаляет только retake).
- **Перф**: `_resolve_owner_locale` кэширует локаль владельца в Redis
  (`assessment_shared.owner_locale_cache_key` → `report:v4:loc:{id}`), чтобы
  горячий `GET /result` (поллинг ~2с при генерации + каждая загрузка страницы)
  не делал join `assessment→profile→user` перед каждым попаданием в кэш.
  Инвалидируется на retake и в `PATCH /auth/me` при смене `users.locale`
  (`report_service.invalidate_owner_locale_cache` — чистит loc-указатель +
  per-locale report-кэш всех ассессментов пользователя). TTL указателя —
  короткий (`OWNER_LOCALE_CACHE_TTL`, 5 мин), **не** 24ч отчёта: инвалидация
  best-effort (`safe_redis_delete` глотает `RedisError`), поэтому молча
  пропущенный `DELETE` не должен держать не тот язык сутки — указатель дёшево
  пересчитать одним запросом.
- Фронт (`Profy-Frontend/src/pages/results/hooks/useResults.ts`): локаль
  владельца (`useLocaleStore.locale`, сырое значение — может быть `kk` до
  KZ-603) входит в `queryKey`; смена языка → рефетч → `GET` 404 → `queryFn`
  прозрачно зовёт `POST /generate` (тот же путь, что и при первой генерации).
  Отчёт **не стирается** императивно при смене локали: `result`-стор помнит
  локаль, под которой отчёт получен (`reportLocale`, `null` = «текущая», как
  ставит `ResultLoadingPage` сразу после генерации); при несовпадении хук
  просто перестаёт считать сохранённый отчёт актуальным для гейта запроса, но
  продолжает показывать его как fallback, пока не придёт новый — упавший
  рефетч (5xx) больше не оставляет пустую страницу с ошибкой, а адаптация
  серверной локали после логина (LocaleGate `ru→kk`) не сносит только что
  сгенерированный отчёт. Пока дремлет — переключатель языка включит KZ-603.
- Контракт: `docs/frontend-result-api-contract.md` §8a.
- Тесты: `test_result_locale.py::test_get_report_signals_locale_not_generated_vs_not_found`,
  `test_ai_artifact_locale_key.py` (в т.ч. `test_resolve_report_three_state_from_one_query`,
  `test_owner_locale_pointer_uses_a_short_ttl`).

## 10. Язык в LLM-промптах

Язык ответа модели задаётся явной инструкцией по локали
(`app/prompts/_locale.py::language_directive(locale)`), а не прозой в системном
промпте. Для `kk` инструкция дополняется глоссарием (названия профессий — как в
казахском каталоге направлений; `ЕНТ` → `ҰБТ`; названия вузов не транслитерировать).

Ответ модели проверяется на язык (эвристика казахских букв `ә ғ қ ң ө ұ ү һ і`);
при несовпадении — ретрай, затем детерминированный `kk`-фолбэк, но не отдача
русского ИИ-текста. Детали — тикеты KZ-401, KZ-402, KZ-403.

## 11. Границы scope перевода

**Переводим:**
- весь пользовательский UI фронта (кроме админки — см. ниже);
- вопросы всех тестов, мотивационные утверждения/пары, каталог направлений и
  профессий;
- детерминированные тексты сервисов (лейблы уровней, гэп-анализ, оверлеи цели,
  каталог ресурсов), фолбэк-нарратив и фолбэк-роадмап;
- письма (подтверждение почты, сброс пароля);
- ИИ-генерацию (отчёт, роадмапы, inquiry);
- описания вузов и программ (`University.description`, `Program.description`,
  `Program.who_its_for`) — LLM-пакетным переводом в `*_i18n["kk"]`, тикеты
  KZ-501 / KZ-504.

**Не переводим:**
- `Program.name`, `University.name` — официальные названия специальностей и вузов.
- Админ-панель `/admin/*` — внутренний инструмент команды, остаётся `ru`-only.
  Строки не выносятся, `t()` в админ-компонентах не используется, пути
  `src/pages/admin/**` и `src/shared/ui/admin/**` — в списке исключений CI-гарда
  (тикет KZ-210).

## 12. Требования приёмной кампании и школьные предметы (KZ-503)

**Термины приёма.** Единственный бэкенд-дом пары ЕНТ/ҰБТ —
`app/i18n/catalog/subjects.py::admission_terms` (`ent`, `profile_subjects`,
`threshold_score`, `creative_exam`; `RU`/`KK`). Глоссарий ИИ-промптов
(`app/prompts/_locale.py::glossary_block`, KZ-401) строит правило
«`ЕНТ` орнына `ҰБТ`, …» из этого каталога — своей копии терминов не держит.
`ЕНТ` и `ҰБТ` не смешиваются в пределах одной локали (CI-гард KZ-602).

**Школьные предметы.** `app/i18n/catalog/subjects.py::school_subjects` —
`{канон. рус. строка → отображаемое имя}`, `RU`/`KK`. Ключ = точное значение,
которое фронт кладёт в `profiles.subjects_liked` / `subjects_easy`
(`SUBJECT_OPTIONS[].value` в `ProfileSetupPage.tsx`, отображение — код
`subject.*` в `onboarding.json`). Рус. строка — **локаль-независимый ключ
матчинга**; каталог только резолвит её в имя.

- Синхронизация BE↔FE: 13 канонических строк. Бэк — `subjects.py`, тест
  `tests/unit/test_subjects_catalog.py` (набор заморожен). Фронт —
  `scripts/i18n-subjects.mjs` (в `npm run i18n:check`): каждый `value` в
  каноническом наборе, каждый `key` резолвится в ru и kk, `ru` строка ==
  `value`. Правка списка — обе стороны сразу.
- Потребитель на бэке: `report_narrative_context._subject_evidence` —
  `text` = имя предмета в локали владельца отчёта (`tr("subjects")` под
  `i18n.use_locale()`), `source_id` остаётся на канонической рус. строке
  (стабильность/дедуп evidence-id). Кастомный предмет вне списка — как есть.
- Гэп-анализ (`gap_analysis_service`) предметные строки не показывает:
  `GapItem.requirement` — это сырой ключ `requirements` (англ.), `comment`
  уже локализован каталогом `gap_analysis` (KZ-307). `Program.requirements.exams`
  / `notes` — сырые ru-данные вузов (не UI-копия, исключены как KZ-206).

## 13. Каталог вузов/программ — `*_i18n`-оверлеи (KZ-501)

Свободный текст каталога (`University.description`, `Program.description`,
`Program.who_its_for`) хранит **одну** русскую строку в основной колонке. Рядом
— nullable `JSONB`-оверлей `{"kk": "..."}` (`*_i18n`), в котором лежат только
не-`ru` переводы; `ru` в оверлей не дублируется. Это НЕ «вариант A» (там строка
на локаль в отдельной таблице) — здесь одна строка, а перевод навешивается
поверх.

- **Read-side.** `app/i18n.resolve_column_i18n(overrides, base_ru, locale)` →
  `(text, resolved_locale)`: отдаёт оверлей, если для локали есть непустое
  значение, иначе `base_ru` (и `resolved_locale = "ru"`). Никогда не бросает —
  `base_ru` может быть `None` (описания вовсе нет), а отсутствие перевода
  нормально до KZ-504. `university_service._university_brief` / `_program_brief`
  / `get_program_detail` строят ответ через него; роутер `university.py`
  передаёт `get_locale()`.
- **API-ответ.** `UniversityBrief` / `ProgramBrief` несут `description_locale`,
  `ProgramDetail` — ещё и `who_its_for_locale` (`"kk"` / `"ru"` — что реально
  отдано). Фронт по расхождению `*_locale != UI-локаль` показывает
  неблокирующую плашку «описание только на русском» (KZ-502).
- **Заполнение — один файл, один скрипт.**
  `scripts/data/catalog_descriptions_kk.json` — единственный источник kk-перевода
  описаний вузов/программ: `{ "universities": [ {slugs, ru, kk} ], "programs":
  [ {rows, ru, kk} ] }`, по одной записи на уникальную `ru`-строку (правишь `kk`
  на месте). `scripts/apply_catalog_descriptions_kk.py` с подкомандами: `apply`
  (файл → `description_i18n['kk']`, идемпотентно, `ru`-колонки не трогает; строки
  ссылаются на ряды портабельным ключом через `entity_resolver`),
  `dump` (ряды БД без перевода → `catalog_descriptions_kk.todo.json`),
  `merge` (заполненный todo → назад в основной файл, с проверкой, что `kk`
  действительно казахский). В runbook — единственная строка `apply` в `start.sh`
  сразу после `build_universities.py`; `cd.yml` / `cd-dev.yml` не менялись.
  `build_universities.py` пишет только `ru`-колонки, `*_i18n` не касается —
  перевод переживает пересборку каталога. Направления (`direction_content_review_kk.json`)
  идут отдельно, через `apply_direction_content.py` (нулевых новых строк в runbook).
- Мелкие поля (`cost_label`, `ranking_label`, `location`, город/страна) `*_i18n`
  не получают — форматируются/локализуются на фронте справочником (KZ-502 /
  KZ-209).
- Пока оверлеи пусты, ответ API байт-в-байт прежний, а `kk` всё равно
  недоступен в рантайме (`SUPPORTED_LOCALES == ("ru",)` до KZ-603), так что
  `get_locale()` возвращает `"ru"` и фолбэк-ветка — единственная активная.

## 14. CI-гарды локализации (KZ-602)

Единственный PR-гейт для i18n (в репо нет CI на PR, только `cd.yml` на push).
Workflow `.github/workflows/i18n-guard.yml` в обоих репозиториях, триггер
`pull_request`.

- **Фронт:** `npm run i18n:check` (парити `ru↔kk`, покрытие плюралов, свип
  нелокализованной кириллицы вне каталога, синк школьных предметов BE↔FE) +
  `npm run typecheck`. Список исключений — `scripts/i18n-exclude.json` (только
  `admin/**` по KZ-210).
- **Бэк:** postgres + redis сервисы → миграции → сид bank-контента (8 скриптов,
  не вся CD-цепочка) → `pytest` целевого i18n-набора + `tests/guard/`.
  - `tests/guard/test_i18n_leak.py`: (1) весь текст нарратива `kk`-отчёта
    проходит `report_narrative_validator._check_language_kk` (нулевой RU-leak);
    (2) `kk`-ответ `ProgramDetail` вне allowlist не содержит русских
    слов-маркеров; (3) `ЕНТ`/`ҰБТ` не смешиваются в пределах локали
    (`subjects.admission_terms`, каталоги `university_requirements`/`gap_analysis`,
    глоссарий промпта).
  - Конфиг гарда — `tests/data/i18n_guard_config.json` (`always_raw_fields`
    — официальные названия/сырые данные вузов, навсегда; `catalog_temp_allowlist`
    = `["description", "who_its_for"]` — **временно до KZ-504**, тест
    `test_guard_config_temp_allowlist_is_only_kz504_pending_fields` не даёт
    расширить; `ru_marker_words`; `ent_terms`).

---

## История решений

| Дата | Решение |
|---|---|
| 2026-09-02 | Зафиксирован контракт; принято: react-i18next, вариант A хранения контента, `users.locale`, без feature-flag, описания вузов переводятся LLM-пакетно, админка `ru`-only. |
| 2026-09-04 | KZ-501: каталог вузов/программ получает `*_i18n`-оверлеи поверх `ru`-колонки (не «вариант A»); read-side — `resolve_column_i18n`, в ответе — `description_locale` / `who_its_for_locale`. |
| 2026-09-04 | KZ-503: `app/i18n/catalog/subjects.py` — единый дом школьных предметов (ключ = канон. рус. строка) + терминов ЕНТ/ҰБТ; глоссарий KZ-401 строится из него; `_subject_evidence` локализует имена предметов; синк BE↔FE тестами (`test_subjects_catalog.py` / `i18n-subjects.mjs`). |
| 2026-09-04 | KZ-602: CI-гарды `.github/workflows/i18n-guard.yml` в обоих репо (PR-гейт); BE `tests/guard/` + конфиг `tests/data/i18n_guard_config.json` (RU-leak в нарративе/каталоге, `ЕНТ`↔`ҰБТ`). |
| 2026-09-08 | KZ-504/505: авторинг-скрипты kk-каталога свёрнуты в один `scripts/apply_catalog_descriptions_kk.py` (`apply`/`dump`/`merge`); `catalog_descriptions_kk.json` переведён в секционный distinct-формат (2357 вузов + 185 программ на 2399+1398 рядов); удалены `export_catalog_kk_todo.py`, `kz505_slice.py`, `kz505_apply.py`, `apply_direction_fields_kk.py`, `apply_direction_subjects_kk.py` и весь батч-мусор `scripts/data/{kk_*,batch_*}`; `start.sh` +1 строка (`apply`) после `build_universities.py`, CD не тронут. `description_i18n['kk']` применён локально: 2399 вузов + 1398 программ. |
