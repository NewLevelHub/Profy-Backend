# Result API v2 — контракт для фронтенда

Статус: **реализовано на ветке `New-Test-Logic`, актуально по коммиту `a67633c`**
("Merge pull request #52 from NewLevelHub/pro-169", 2026-08-14).

В отличие от предыдущей версии этого документа (которая описывала v2 как
согласованный, но ещё не реализованный контракт), student-facing v2-форма
уже реально собирается и отдаётся эндпоинтами `/result/generate` и
`/result/{assessment_id}` — код, схемы и тесты ниже подтверждены построчным
чтением `app/routers/result.py`, `app/schemas/result_v2.py`,
`app/services/report_service.py`, `app/services/report_v2_assembler.py`,
`app/services/report_narrative_service.py` /
`app/services/report_narrative_fallback.py` и
`app/models/analysis_result.py`.

Есть несколько мест, где реальность отличается от старого согласованного
черновика — они помечены **[РАСХОЖДЕНИЕ]** ниже. Есть и поля, которых в
реальном коде ещё нет вовсе — они помечены **[ASPIRATIONAL — не реализовано]**.
Фронт должен ориентироваться на код, а не на память об исходном
согласовании.

`AdminAnalysisResultResponse` (`app/schemas/admin_result.py`) остаётся
отдельной raw/admin-формой (`profile`, `meta`, `match_score`, `big_five`,
`personality_profile`, `motivation_top` и т.д.) — это не то, что видит
студент, и не тот объект, который описывает этот документ.

## 1. Эндпоинты

```text
POST /api/v1/result/generate
Content-Type: application/json
Authorization: Bearer <token>

{"assessment_id": "uuid"}

GET /api/v1/result/{assessment_id}
Authorization: Bearer <token>
```

Оба эндпоинта возвращают одну и ту же student-safe форму —
`response_model=ResultV2Schema` (дискриминированный union, см. §4), без
отдельного "raw" ответа для студента. `assessment_id` в обоих случаях
проверяется на принадлежность текущему пользователю через
`Profile.user_id` (см. §8).

**[РАСХОЖДЕНИЕ]** Повторный `POST /result/generate` не перегенерирует
narrative — если `AnalysisResult` для этого `assessment_id` уже существует
в БД (или в кэше), обе ручки просто возвращают уже сохранённый результат.
Это совпадает с тем, что обещал черновик, но стоит явно подтвердить: нет
скрытого "regenerate" флага и нет способа с фронта форсировать пересчёт —
единственный способ получить новый отчёт — invalidate retake (см. §8).

## 2. Возрастные ветки assessment

- **junior (6–9)**: MI + Big Five + Harter-парные вопросы по мотивации.
  RIASEC и career matching не используются — `interest_instrument = "mi"`.
- **middle (10–13)**: RIASEC + Big Five + Harter-парные вопросы по
  мотивации. `interest_instrument = "riasec"`.
- **senior (14–18)**: RIASEC + Big Five + MOST/LEAST мотивационные триплеты.
  `interest_instrument = "riasec"`.

Ветка определяется `Profile.age_group` в момент генерации
(`report_service.build_report`); при чтении уже сохранённого результата
(`GET`, повторный `POST`) `interest_instrument` вместо этого
восстанавливается из формы сохранённого `AnalysisResult.profile` —
`report_service._stored_interest_instrument` смотрит, есть ли в ключах
RIASEC-буквы (`R/I/A/S/E/C`); если нет — считается MI. Так что после
merge PR #52 фронту всё ещё правильно ветвиться по `interest_instrument`
из ответа, а не по возрасту пользователя — на этот раз не как
подстраховка "на будущее", а потому что backend сам определяет ветку не
всегда напрямую по `age_group`.

Motivation input-flow различается по возрасту (Harter-пары vs.
MOST/LEAST-триплеты), но студенту он унифицирован — всегда только
`motivation_highlights` (список коротких фраз, не сырые категории).

## 3. Общая форма ответа

Все поля ниже — реальные поля `_ResultResponseBase`
(`app/schemas/result_v2.py`), общие для обеих веток. Пример — санитайзнутый
вариант senior-снапшота (`tests/snapshots/result_v2_example_senior.json`),
с более реалистичными текстами вместо тестовых заглушек:

```jsonc
{
  "report_version": 2,
  "assessment_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "interest_instrument": "riasec",
  "summary": "По твоим ответам заметно, что тебе интересны определённые сферы...",
  "disclaimer": "Это не окончательный выбор, а карта возможных направлений — со временем картина может измениться, и это нормально.",
  "strength_cards": [
    { "title": "Любишь докапываться до сути и разбираться, как всё устроено", "description": "Это заметно по тому, какие ответы ты выбирал(а) в тесте." }
  ],
  "interest_map": [
    { "code": "R", "sphere": "Практика и техника", "level": "medium" }
  ],
  "interest_map_note": "Ярко выражено: ... . Остальные сферы проявляются тише — и это нормально.",
  "thinking_style_notes": [
    { "title": "Тебе близко системное мышление", "description": "..." }
  ],
  "personality_notes": [
    { "trait": "openness", "label": "Открытость новому", "description": "..." }
  ],
  "personality_note": "Ярко выражено: ... — это то, что тебе, скорее всего, даётся естественнее всего.",
  "motivation_highlights": ["Тебе важно разбираться в интересных задачах."],
  "is_flat_profile": false,
  "exploration_note": "Не обязательно пробовать всё сразу — начни с того, что откликается больше всего...",
  "final_analysis": "Если сложить всё вместе: твои интересы показывают, куда тебя тянет...",
  "careers": [ /* см. §5, [] для mi */ ],
  "exploration_activities": [ /* см. §4, [] для riasec */ ],
  "created_at": "2026-08-07T08:00:00Z"
}
```

**[РАСХОЖДЕНИЕ]** По сравнению со старым черновиком форма реально шире:

- `disclaimer` — фиксированная, server-authored строка (не LLM), показывается
  рядом с `summary` всегда одна и та же. В черновике этого поля не было.
- `interest_map_note` — 1-2 предложения поверх `interest_map`, детерминированно
  строится в `report_v2_assembler.build_interest_map_note` (не LLM). Раньше
  не упоминалось.
- `personality_notes` (список из ровно 5 карточек, по одной на домен Big
  Five: `openness`, `conscientiousness`, `extraversion`, `agreeableness`,
  `emotional_stability`) и `personality_note` (1-2 предложения синтеза) —
  реальная секция "Твой характер", присутствует на обеих ветках и не
  зависит от `interest_instrument` (Big Five отвечают одинаково все три
  возраста). **Важно:** это не то же самое, что admin-only
  `AnalysisResult.personality_notes` — это другое, публичное поле с другой
  структурой (`{trait, label, description}` вместо `{trait: phrase}`).
  Черновик перечислял `personality_notes` в списке "никогда не отдавать
  студенту" (§6 старой версии) — это было верно для сырого admin-поля, но
  вводило в заблуждение по поводу v2-контракта: студенту **отдаётся** поле
  с таким же именем, но другой формы и назначения. Backend не течёт сырыми
  Big Five баллами — экспозиции сырых данных нет, но имя поля совпадает,
  и фронту стоит об этом знать при чтении схем.
- `exploration_note` — фиксированный закрывающий текст под
  `exploration_activities` (junior), присутствует и на riasec-ветке (где
  `exploration_activities` пуст), фронт просто не рендерит его в этом
  случае.
- `final_analysis` — 3-5 предложений синтеза, LLM-generated либо
  deterministic fallback, показывается последним на странице.

## 4. Discriminated interest contract

Контракт — реальный дискриминированный Pydantic-union по
`interest_instrument` (`MiResultResponse` | `RiasecResultResponse`,
`app/schemas/result_v2.py`), а не соглашение "по факту": конструктор с MI +
непустым `careers` или RIASEC-веткой с 8 элементами `interest_map` реально
не проходит валидацию Pydantic на backend (`ValidationError`), это
enforced на уровне схемы, а не только "так собирает ассемблер".

### `interest_instrument = "mi"` (junior)

- `interest_map` — ровно 8 элементов (`Field(min_length=8, max_length=8)`),
  ключи `verbal`, `logical`, `musical`, `visual`, `bodily`,
  `interpersonal`, `intrapersonal`, `naturalistic`, в этом порядке
  (`mi_service.MI_ORDER`).
- `careers` — всегда `[]`, зафиксировано на уровне схемы
  (`max_length=0`) — backend не может отдать junior непустой `careers`,
  даже по ошибке.
- `exploration_activities` — непустой список строк, минимум 1 элемент
  (`Field(min_length=1)`). Строится из `MI_ACTIVITIES` по топ-категориям
  студента; если ни одна категория не набрала evidence, backend отдаёт по
  одной активности на каждую MI-категорию как safe fallback — список
  никогда не пуст.

### `interest_instrument = "riasec"` (middle/senior)

- `interest_map` — ровно 6 элементов (`R`, `I`, `A`, `S`, `E`, `C`, в этом
  порядке — `riasec_service.HOLLAND_ORDER`). `code` — буква Holland-кода,
  но UI обязан показывать `sphere`, а не букву.
- `careers` — максимум 5 элементов (`Field(max_length=5)`); для flat
  profile — ровно 3, все `tier="worth_trying"` (enforced
  model-валидатором `_flat_profile_has_exactly_three_worth_trying_careers`
  на самой схеме, не только в ассемблере).
- `exploration_activities` — зафиксирован пустым на уровне схемы
  (`max_length=0`) для riasec-ветки. **[РАСХОЖДЕНИЕ]**: черновик говорил
  "отсутствует или пуст согласно финальной OpenAPI-схеме" осторожно, как
  про нерешённый вопрос — на деле поле **присутствует всегда** (это общее
  поле базовой модели), просто гарантированно `[]` для riasec. Фронту не
  нужно обрабатывать случай "поля вообще нет в ответе".

Фронт обязан ветвиться по `interest_instrument`, а не по возрасту или виду
`code` — подтверждено: при чтении уже сохранённого результата backend сам
восстанавливает `interest_instrument` не из возраста, а из формы сырых
данных (см. §2).

## 5. Career item (только RIASEC)

Реальная форма `StudentCareer` (`app/schemas/result_v2.py`):

```jsonc
{
  "slug": "software-developer",
  "name": "Разработчик программного обеспечения",
  "rank": 1,
  "tier": "strong", // rank 1 = strong; rank 2-3 = good; rank 4-5 = worth_trying; flat profile = всегда worth_trying
  "why": "Совпадает с тем, что у тебя выражено: любишь разбираться в сложных задачах.",
  "matched_strengths": ["Любишь разбираться в сложных задачах"],
  "try_now": "Собери маленький проект и отметь, какая часть понравилась.",
  "description": null,
  "skills_needed": [],
  "subjects_to_develop": []
}
```

`why` и `try_now` гарантированно непустые (`Field(min_length=1)`) — если у
направления нет подтверждённого RIASEC-совпадения, backend подставляет
нейтральный fallback-текст (`riasec_content.NEUTRAL_CAREER_WHY` /
`NEUTRAL_TRY_NOW`), а не пустую строку. `matched_strengths` легитимно
пуст именно в этом fallback-случае.

**[РАСХОЖДЕНИЕ]** У черновика в примере career item было поле
`first_steps: []` — в реальной схеме такого поля нет вовсе. `first_steps`
существует только как внутреннее сырое поле `Direction`/admin-каталога;
студенту из него отдаётся ровно один элемент, уже смэпленный в `try_now`.
Не рендерить/не ждать `career.first_steps` на фронте.

Порядок `careers` — уже финальный ranking с backend (по `match_score`),
фронт не должен пересортировывать список.

## 6. Что student API не возвращает

Подтверждено чтением `ResultResponseV2`/`_shape_response`/
`assemble_result_v2` — ни один из следующих admin-only ключей не попадает
в student-ответ ни при каком пути (генерация, кэш-хит, повторный `GET`):
`profile` (сырые баллы по буквам/MI-ключам), `code` (топ-код), `meta`
(differentiation/consistency/aversion), `match_score`, сырые
`strengths`/`weaknesses`, `development_plan`, `big_five` (сырые баллы Big
Five), сырой `personality_profile` (0-100 по трейту), сырой `thinking_style`
(0-100 по 4 стилям), сырое `motivation` (0-100 по категориям),
`motivation_top` (список сырых категорий).

Не показывать проценты, баллы, диагнозы, сравнительные ярлыки или выводы о
способностях/будущей успешности — весь текст студенту идёт либо через
LLM-narrative pipeline с валидатором (`report_narrative_validator.py`),
либо через deterministic fallback, построенный из того же evidence-каталога.

**Важное уточнение к списку выше:** публичные `personality_notes` (список
карточек) и `personality_note` (строка синтеза) в этом списке "запрещённых"
быть не должны — это легитимные, целенаправленно спроектированные
public-поля v2-контракта (см. §3), просто с тем же именем/похожим именем,
что и внутренние raw-поля `AnalysisResult`. Не путать одно с другим при
чтении схем/интеграции.

## 7. Flat profile

- `is_flat_profile` вычисляется backend'ом
  (`report_v2_assembler.is_flat_profile`) как
  `differentiation < 25.0` (разброс между макс. и мин. категорией <25
  пунктов на нормализованной 0-100 шкале) — фронт не пересчитывает
  threshold сам.
- RIASEC: ровно 3 `careers`, все с `tier="worth_trying"` — гарантировано
  Pydantic-валидатором на самой схеме (см. §4), а не только логикой
  ассемблера.
- Если у flat-профиля студента есть self-reported артефакты в профиле
  (`Artifact`), `summary` получает добавочное предложение
  (`_FLAT_PROFILE_ARTIFACT_NOTE`), объясняющее, что при близких RIASEC-баллах
  стоит присмотреться и к направлениям, связанным с этими увлечениями —
  это единственная мягкая митигация того, что flat-профиль по чистому
  RIASEC top-3 может дать шумные/нерелевантные career matches (известный,
  осознанный gap методологии — полноценное решение — это отдельная задача
  по переработке career matching, не в этом контракте).
- MI: `careers` остаётся пустым (как и во всех junior-случаях),
  `summary`/`exploration_activities` не утверждают о "слабом результате" —
  тон подобран так же, как и для не-flat профиля.

## 8. Completion и ошибки

`POST /result/generate` использует собственную server-side проверку
завершённости (`report_service._assert_assessment_complete`), не
полагаясь на клиентский флаг `completed` с `/assessment/answers` или
`/assessment/motivation` — каждый из них подтверждает только свою фазу:

- Likert-часть (RIASEC/MI + Big Five вместе) должна быть отвечена
  полностью: `likert_answered_count >= likert_total_questions(age_group)`.
- Мотивационная часть — по своей таблице в зависимости от возраста:
  Harter-пары (`motivation_pair_service`) для junior/middle, MOST/LEAST
  триплеты (`motivation_service`) для senior — обе должны быть отвечены
  полностью.
- Если хотя бы одно из двух не завершено — **`409 Conflict`**
  (`"Тест ещё не завершён — сначала ответь на все обязательные вопросы"`).
  Assessment при этом не переводится в `completed` и никакой (даже
  частичный) `AnalysisResult` не создаётся — это в одной транзакции с
  переводом статуса.

Остальные коды, подтверждённые чтением роутера (`app/routers/result.py`):

- **`404`** — assessment с данным `assessment_id` не найден (обе ручки).
  На `GET` также `404`, если assessment найден и принадлежит пользователю,
  но `AnalysisResult` на локали владельца не сгенерирован — с
  `error_code: "report_locale_not_generated"` когда отчёт есть на другой
  локали (KZ-406, см. §8a), иначе `{"detail": "Report not found"}`.
- **`403`** — assessment принадлежит другому пользователю (owner
  проверяется через join `Assessment -> Profile.user_id`).
- **`409`** — обязательные ответы ещё не завершены (см. выше).

Ошибка LLM или Redis не превращается в `5xx`:

- LLM: `report_narrative_service.generate_report_narrative` делает до 3
  попыток (1 первичная + 2 corrective retry с описанием, что именно не
  прошло валидацию), и если ни одна не прошла (или LLM выключен
  конфигом) — детерминированно строит narrative через
  `report_narrative_fallback.build_fallback_narrative` на основе того же
  evidence-каталога, что использовал бы LLM-путь. Функция never raises —
  студент всегда получает валидный 200 той же v2-формы, просто без
  LLM-персонализации текста.
- Redis: и чтение, и запись кэша обёрнуты в try/except на
  `aioredis.RedisError` — недоступность Redis логируется и код падает
  через на DB-путь (для чтения) или просто не кэширует (для записи), но
  никогда не превращается в ошибку ответа. Кэш-запись, сериализованная до
  добавления нового обязательного поля в схему, тоже не ломает ответ —
  `_cache_get_response` ловит `ValidationError` при десериализации и
  просто перестраивает ответ из БД.

Повторный `POST` и `GET` возвращают сохранённый результат (кэш или БД), а
не запускают скрытую перегенерацию narrative — единственный способ
получить новый отчёт с фронта — полный retake, который инвалидирует кэш
(`assessment_shared.report_cache_key` / инвалидация на retake, добавленная
в PR #52).

## 8a. Локаль отчёта (KZ-403 / KZ-405 / KZ-406)

**Язык отчёта определяет бэкенд по владельцу артефакта — `users.locale`
ученика, — а не по `Accept-Language` запроса.** Админ на `ru`, открывающий
`/results` `kk`-ученика, всё равно получает `kk`-отчёт. `kk` физически вне
`SUPPORTED_LOCALES` до KZ-603, но `users.locale` уже может быть `kk`
(`KNOWN_LOCALES`), и генерация/выдача это учитывают.

- Хранение и кэш — **на пару `(assessment_id, locale)`**: строка в
  `analysis_results` с колонкой `locale` (составной unique), Redis-ключ
  `report:v4:{locale}:{assessment_id}`. `ru` и `kk` версии независимы.
- **Детерминированные части идентичны между локалями** — счёт тестов,
  `code`, `strengths`, `interest_map.level`, топ-профессии, career-matching.
  Между `ru` и `kk` меняется только текст (summary, карточки, `*_note`,
  названия направлений/сфер).
- `POST /result/generate` генерирует отчёт **на локали владельца**; если
  строки на этой локали нет — создаёт её (не трогая строку другой локали).
- `GET /result/{id}` отдаёт строку **только на локали владельца**. Если её
  нет:
  - `404` + `{"error_code": "report_locale_not_generated", "detail": "…"}`
    — отчёт есть на другой локали, нужно лениво пересоздать: клиент
    показывает статус генерации и делает `POST /result/generate`;
  - `404` + `{"detail": "Report not found"}` (без `error_code`) — отчёта
    нет ни на одной локали (обычная «ещё не сгенерирован»).

**Что делает фронт при смене языка** (`useResults`): локаль владельца
входит в `queryKey` (`['result', assessmentId, locale]`); смена языка →
React Query рефетчит → `GET` 404 (`report_locale_not_generated`) → `queryFn`
прозрачно вызывает `POST /result/generate` (тот же ленивый путь, что и при
самой первой генерации), скелет/оверлей показывается через `isLoading`.
Обратное переключение отдаёт исходную строку той локали без повторной
генерации. Retake удаляет строки и кэш **всех** локалей.

`PATCH /auth/me` со сменой `locale` инвалидирует серверный report-кэш всех
ассессментов пользователя (per-locale payload'ы + внутренний указатель на
локаль владельца) — поэтому первый `GET /result` после переключения языка
всегда резолвит новую локаль, а не отдаёт закэшированный старый payload.

## 9. Что ещё аспирационно / не реализовано

- Admin-configurable flat-profile threshold и tuning career-matching
  матрицы по не-RIASEC сигналам (упомянуто в комментариях
  `report_v2_assembler.py` со ссылкой на TZ_Profi.md §16.4 и
  result-quality-fixes.md §3) — **[ASPIRATIONAL]**, порог `25.0` сейчас
  захардкожен константой, полноценного решения проблемы "шумного" flat
  top-3 (только текстовая митигация через артефакты, см. §7) нет.
  Не полагаться на возможность настроить это через API.
- Явного публичного OpenAPI-описания "student cannot request raw result"
  как отдельного эндпоинта нет — раздельность admin/student обеспечена
  тем, что `/result/*` использует только `ResultV2Schema`, а
  `AdminAnalysisResultResponse` живёт в отдельном (не описанном здесь)
  admin-роутере с отдельной авторизацией.
