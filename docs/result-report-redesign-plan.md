# Редизайн student `/result` под ТЗ §17–18

## Вердикт по исходной доке

Основное направление верное: student-ответ нужно отделить от admin raw-ответа, скрыть численные скоры, хранить персонализированный narrative и иметь детерминированный fallback. До реализации в документе нужно исправить следующие несоответствия фактическому коду и ТЗ [`TZ_Profi.md`](/Users/yessimkhanuly13/Downloads/TZ_Profi.md):

- Реальные маршруты: `POST /api/v1/result/generate` и `GET /api/v1/result/{assessment_id}`, а не общий `GET/POST /api/v1/result` ([`app/routers/result.py`](/Users/yessimkhanuly13/Desktop/Profy-Backend/app/routers/result.py)).
- ТЗ требует initial generation + до двух регенераций, то есть максимум 3 content-attempts (§17.7–17.8), а не 2. Транспортный retry внутри [`llm_client.complete_json`](/Users/yessimkhanuly13/Desktop/Profy-Backend/app/services/llm_client.py) считается отдельно.
- Одной структурной проверки недостаточно: обязательны stop-word validator по §3.1/Приложению C, проверка длины, языка и новых чисел/фактов; каждый провал логируется.
- Нельзя оставлять `careers_why` пустым в fallback: §18.2 требует объяснение для каждого показанного направления. Fallback обязан дать непустое, детерминированное `why` из разрешённых сигналов.
- `riasec_content.py` уже существует; его нужно расширить student-facing названиями сфер и fallback-фразами, а не создавать заново ([`app/services/riasec_content.py`](/Users/yessimkhanuly13/Desktop/Profy-Backend/app/services/riasec_content.py)). При этом ТЗ требует редактируемый из админки mapping сильных сторон (§18.2), поэтому статическая таблица допустима только как безопасный системный fallback, не как окончательный источник контента.
- `personality_notes` сейчас не хранит tier: это `dict[trait, text]`. High-сигналы нужно определять сервером из `personality_profile` и передавать LLM уже как безопасные categorical refs, без float ([`app/services/bigfive_content.py`](/Users/yessimkhanuly13/Desktop/Profy-Backend/app/services/bigfive_content.py)).
- Текущий `_build_summary` раскрывает RIASEC-код и «типы», что нарушает §2.2/§3.1. Fallback должен говорить об интересах и наблюдаемом поведении без букв, кода и типологизации ([`app/services/report_service.py`](/Users/yessimkhanuly13/Desktop/Profy-Backend/app/services/report_service.py)).
- «Весь отчёт адаптирован по возрасту» не выполняется, если `motivation_highlights`, career details и fallback одинаковы для всех. Нужно задать серверные лимиты/глубину для каждого age group, а не полагаться только на инструкцию промпту.
- Исключать flat-profile нельзя: §16.6 требует top-3 с `worth_trying`, специальный summary и admin-флаг. Именно shaping `/result` должен использовать сохранённую `meta.differentiation`; публично `meta` не отдаётся.
- Текущее `matched_careers` сортирует tie только по `match_score`; DB-порядок при равенстве не гарантирован. Перед rank-tiering нужен стабильный secondary key, иначе одинаковые результаты могут менять tier между запросами ([`app/services/riasec_service.py`](/Users/yessimkhanuly13/Desktop/Profy-Backend/app/services/riasec_service.py)).
- `Direction` сейчас фактически содержит отдельные профессии и seed заполняет только `name + holland_code`; `description/professions/skills/subjects/first_steps` пусты ([`scripts/seed_riasec_directions.py`](/Users/yessimkhanuly13/Desktop/Profy-Backend/scripts/seed_riasec_directions.py)). Поэтому этот заход не закрывает §18.2 п.6–7 целиком. Контракт должен честно разрешать пустые content-поля/не рендерить их, а отдельная taxonomy/content-задача должна развести «направление» и «профессии внутри».
- Текущий `build_report` преждевременно переводит assessment в `completed`, не проверяет полноту Likert + motivation и коммитит статус отдельно от `AnalysisResult`. Это допускает completed assessment без отчёта и генерацию по частичным ответам; redesign должен добавить completion gate и одну согласованную транзакцию.
- После merge `origin/New-Test-Logic` интересы больше не означают один инструмент для всех возрастов: junior хранит в `AnalysisResult.profile/code/meta` 8 MI-категорий и не получает career matching, middle/senior — 6 RIASEC-категорий и careers. Эти JSONB-поля теперь семантически полиморфны, поэтому student contract обязан иметь явный discriminator, а raw/admin-схема не должна называться только RIASEC.
- Мотивация также имеет два input-flow: junior/middle отвечают Harter-пары через `motivation_pair_service`, senior — MOST/LEAST triplets через `motivation_service`. Оба flow намеренно сводятся к тем же `motivation`, `motivation_top` и `motivation_highlights`, поэтому student response не нужно раздваивать, но completion/cache/retake/test paths обязаны учитывать оба сервиса.

## 1. Сначала отделить admin raw contract

- Вынести текущие `CareerMatch`, `RiasecMeta`, `ThinkingStyle`, `DevelopmentPlan` и полный текущий ответ в `AdminAnalysisResultResponse`, предпочтительно в [`app/schemas/admin_result.py`](/Users/yessimkhanuly13/Desktop/Profy-Backend/app/schemas/admin_result.py).
- Переключить [`AdminAssessmentDetailResponse.analysis_result`](/Users/yessimkhanuly13/Desktop/Profy-Backend/app/schemas/admin.py) и [`admin_service.get_assessment_detail`](/Users/yessimkhanuly13/Desktop/Profy-Backend/app/services/admin_service.py) на admin-схему.
- Существующий admin endpoint уже есть; утверждение «если маршрута ещё нет» удалить. UI может быть отдельным scope, backend-route `/api/v1/admin/assessments/{id}` уже возвращает результат.

## 2. Зафиксировать новый student contract до реализации

В [`app/schemas/result.py`](/Users/yessimkhanuly13/Desktop/Profy-Backend/app/schemas/result.py) оставить только безопасную форму:

- `report_version: Literal[2]` для явного breaking contract.
- `summary` с серверно добавленным age-specific disclaimer.
- `strength_cards` из 5–7 карточек без category labels; внутренняя evidence metadata в public JSON не выходит.
- `interest_instrument: Literal["mi", "riasec"]` — обязательный discriminator; фронт не должен определять инструмент по ключам или возрасту.
- `interest_map` сохраняет одну render-friendly форму (`code`, человекочитаемый `sphere`, `level`), но cardinality и порядок зависят от discriminator: junior/MI — 8 элементов в `MI_ORDER`, middle/senior/RIASEC — 6 элементов в фиксированном RIASEC-порядке. `level` — только render-state, фронт не подписывает его словом «низкий» и не красит красным.
- `thinking_style_notes`; существующий безопасный `motivation_highlights` остаётся отдельным смысловым полем. Если мотивационный блок позже тоже станет LLM-generated и age-specific, для него заводится собственная typed JSONB-колонка, а не расширяется общий blob.
- Для `interest_instrument="riasec"`: `careers` максимум 5, а для flat profile — 3. Каждый элемент содержит `rank`, `tier`, обязательный непустой `why`, `matched_strengths`, факты из БД и age-specific `try_now`.
- Для `interest_instrument="mi"`: `careers` всегда `[]`; вместо выдуманного career matching ответ содержит `exploration_activities` из безопасного MI content layer (`development_plan.reinforce`/`MI_ACTIVITIES`). Это поле нельзя потерять при скрытии raw `development_plan`.
- Явно удалить из student schema: `profile`, `code`, `meta`, `match_score`, `strengths`, `weaknesses`, `development_plan`, `big_five`, `thinking_style` floats, `personality_profile`, `personality_notes`, `personality_highlights`, `motivation`, `motivation_top`.

До кодинга создать [`docs/frontend-result-api-contract.md`](/Users/yessimkhanuly13/Desktop/Profy-Backend/docs/frontend-result-api-contract.md), а не после реализации: это breaking change для фронта. Документировать omission пустых direction-content блоков и отдельный flat-profile ответ.

## 3. Сформировать безопасный evidence catalog

В [`report_service.py`](/Users/yessimkhanuly13/Desktop/Profy-Backend/app/services/report_service.py) построить отдельный `ReportNarrativeContext`, не передавать в новый prompt полный `StudentContext`:

- Каждый разрешённый агрегированный сигнал получает стабильный `source_id`: MI category для junior или RIASEC strength/category для middle/senior (в обоих случаях без процента), high personality note, motivation category/highlight, top thinking-style label, liked/easy subject, artifact.
- Для career rationale передавать top direction facts и список допустимых `source_id`, релевантных конкретной карточке.
- LLM output должен возвращать evidence refs для каждой strength card и career rationale. Post-validator проверяет, что refs существуют и разрешены для этого элемента; перед student response refs удаляются.
- Raw `profile`, `big_five`, `motivation`, `meta.aversion`, `match_score` не передавать в narrative prompt: модель не сможет случайно процитировать их.

## 4. Typed JSONB по смысловым полям

Сохранить уже принятое владельцем проекта решение из [`docs/roadmap-goal-contract.md` §3](/Users/yessimkhanuly13/Desktop/Profy-Backend/docs/roadmap-goal-contract.md): одна independently-queryable typed JSONB-колонка на смысловое поле, без единого all-in-one blob.

Новая миграция от текущей Alembic head добавляет в `analysis_results` ровно два новых поля. После reconciliation merge текущая head — `0040`, поэтому на момент этого плана следующий кандидат — `0041`; номер и `down_revision` всё равно нужно получить/проверить непосредственно перед созданием миграции, а не хардкодить из документа:

- `strength_cards JSONB NOT NULL DEFAULT '[]'`;
- `thinking_style_notes JSONB NOT NULL DEFAULT '[]'`.

Остальные части результата используют уже существующие смысловые поля:

- `summary` остаётся отдельной `Text`-колонкой;
- `motivation_highlights` остаётся отдельной существующей JSONB-колонкой;
- top-5 элементов существующего `careers` дополняются `why`, `matched_strengths`, `try_now` и внутренними `evidence_refs`; `match_score` и остальные raw facts не удаляются, а элементы 6–10 остаются без student narrative.

Это сохраняет совместимость с [`student_context.py`](/Users/yessimkhanuly13/Desktop/Profy-Backend/app/services/student_context.py), roadmap и university matching: они продолжают читать полный stored top-10 и игнорируют дополнительные ключи. `report_version=2` — версия публичного контракта и cache namespace, а не основание собирать все поля в один DB blob.

Не допускать неявной перегенерации уже выданного отчёта: `POST /generate` заполняет typed narrative-поля один раз; admin regeneration должна быть отдельной командой. Для старых строк с пустыми массивами/без `careers[].why` нужен явно выбранный rollout-path: безопасный deterministic compatibility shape или контролируемый backfill, но не автоматический повторный LLM-вызов на каждом GET.

University migration уже перенесена в линейный хвост как `0040_add_university_requirements_to_direction_roadmaps.py` (`down_revision="0039"`). Не переиспользовать номера `0034–0040`: они заняты merge-цепочкой MI/Harter + university requirements.

Проверено 2026-08-07 внутри API-контейнера: `alembic heads` возвращает одну
head `0040`; хвост графа линеен:
`0033 → 0034 motivation text → 0035/0036 question-pair overrides → 0037 Harter pairs → 0038 MI → 0039 chosen_side → 0040 university requirements`.

Rollout зависит от фактического состояния окружения:

- БД на `0033` или на новой цепочке `0034–0039` обновляется штатным
  `alembic upgrade head`.
- БД, где до merge уже применялся старый university-`0034`, нельзя обновлять
  вслепую: её `alembic_version=0034` означает другой DDL. Для disposable dev
  предпочтителен reset; для сохраняемой БД — schema audit, применение
  недостающих `0034–0039` и осознанный stamp/reconcile `0040`, если колонка
  `direction_roadmaps.university_requirements` уже существует.
- Перед production rollout проверить и `alembic_version`, и наличие
  `motivation_statements.text_junior`/`direction_roadmaps.university_requirements`;
  один только номер версии недостаточен для окружения со старым `0034`.

## 5. LLM generation и обязательная validation pipeline

Добавить [`app/prompts/report_narrative.py`](/Users/yessimkhanuly13/Desktop/Profy-Backend/app/prompts/report_narrative.py) со strict JSON schema и единым вызовом на отчёт, но учесть все обязательные правила ТЗ:

- Три языка из `Profile.language`, а не только русский; fallback/disclaimer/content mappings тоже должны иметь ru/kk/en либо scope честно маркируется как неполное соответствие ТЗ.
- Три age-depth профиля с серверно проверяемыми лимитами: junior заметно короче senior, middle между ними.
- Полный запрещённый vocabulary из §3.1 и Приложения C; запрет диагнозов, способности/успешность, сравнений, типологических ярлыков и новых фактов.
- Максимум 3 content-attempts. После невалидного structured output добавлять corrective hint; после LLM/validation failure строить deterministic narrative.
- Post-validation: exact slug set, source refs, 5–7 strength cards, требуемое число notes/careers, непустые строки, age length limits, выбранный язык, banned phrases, отсутствие новых чисел/фактов. Все причины логировать структурированно.

ТЗ также требует admin-editable/versioned prompts и strength mapping. Если это не входит в этот PR, вынести двумя явными blocker tickets и не называть hardcoded Python prompt/mapping полным соответствием §17.5/§18.2.

## 6. Полноценный deterministic fallback

- Расширить существующий [`riasec_content.py`](/Users/yessimkhanuly13/Desktop/Profy-Backend/app/services/riasec_content.py) student-facing sphere names и strength templates; для junior использовать [`mi_content.py`](/Users/yessimkhanuly13/Desktop/Profy-Backend/app/services/mi_content.py) как равноправный deterministic source для названий сфер и `exploration_activities`. Добавить age/language variants в оба слоя.
- Добавить [`thinking_style_content.py`](/Users/yessimkhanuly13/Desktop/Profy-Backend/app/services/thinking_style_content.py) и аналогичный безопасный motivation layer либо объединить их в один report-content module.
- Fallback формирует тот же `ReportNarrative` и проходит тот же validator, что AI output.
- `why` строится из первого валидного совпавшего evidence ref и никогда не бывает `null`/пустым.
- Disclaimer добавляется ровно один раз при shaping: хранить narrative summary без disclaimer либо хранить финальный summary, но не смешивать оба подхода.

## 7. Детерминированное shaping, age и flat-profile

- `_shape_response(analysis, profile)` объединяет raw DB facts и stored narrative; никакого `model_validate(analysis)` для student schema.
- `_interest_map` выбирает порядок по `interest_instrument`: `MI_ORDER` (8) для junior и RIASEC order (6) для middle/senior; для обоих используются заранее согласованные absolute thresholds. Не назначать уровни по рангу: flat profile иначе искусственно получит high/low. Рекомендуемый старт для текущей шкалы 1–5: `<50 low`, `50–69.9 medium`, `>=70 high`, с boundary-тестами для обеих cardinality и продуктовым подтверждением.
- `_tier_careers` вызывается только для RIASEC: сначала стабильно сортирует `(-match_score, slug)`, затем назначает rank tiers: 1 strong, 2–3 good, 4–5 worth_trying; score остаётся только в DB/admin. MI-ветка возвращает `careers=[]` без фиктивных tiers.
- Если `meta.differentiation` ниже конфигурируемого flat threshold: для RIASEC — special summary, top-3 careers, все `worth_trying`; для MI — special summary и нейтральные `exploration_activities`, без careers. В обоих случаях public `is_flat_profile=true`; threshold нельзя навсегда хардкодить, потому что §16.6 требует настройку из admin/config.
- Server-side depth limits должны делать junior-отчёт реально в 2–3 раза короче: короткие strength cards и MI activities вместо career cards; static DB arrays тоже обрезаются по age policy.

## 8. Cache и отказоустойчивость

- Перейти на `report:v2:{assessment_id}` и вынести key/invalidation в общий helper.
- Обновить все текущие invalidation sites: [`assessment_service.py`](/Users/yessimkhanuly13/Desktop/Profy-Backend/app/services/assessment_service.py), [`question_pair_service.py`](/Users/yessimkhanuly13/Desktop/Profy-Backend/app/services/question_pair_service.py), [`motivation_service.py`](/Users/yessimkhanuly13/Desktop/Profy-Backend/app/services/motivation_service.py) и [`motivation_pair_service.py`](/Users/yessimkhanuly13/Desktop/Profy-Backend/app/services/motivation_pair_service.py). Исходный план меняет reader key, но оставляет stale v2 cache после retake.
- Redis read/write failures сделать non-fatal; иначе §17.8 всё ещё нарушается даже при идеальном LLM fallback.
- Старые `report:{id}` просто игнорировать; cache всегда хранит уже shaped student JSON v2.
- В `question_pair_service` одновременно закрыть существующий retake-баг: после удаления отчёта вызывается `invalidate_direction_flow`, но не `invalidate_goal_roadmap`, поэтому middle retake может оставить старый goal roadmap.
- В [`tests/conftest.py`](/Users/yessimkhanuly13/Desktop/Profy-Backend/tests/conftest.py) сбрасывать также singleton `report_service._redis`, иначе async integration tests будут переиспользовать клиент из закрытого event loop.

## 9. Completion gate и транзакционная целостность

- До scoring/LLM проверить, что завершены обе части теста теми же функциями counts, которые использует assessment flow; `POST /result/generate` не должен сам объявлять неполный тест завершённым. Motivation count выбирается по возрасту: Harter pairs для junior/middle, triplets для senior; Likert total для junior исключает retired RIASEC rows.
- Статус `completed`, `completed_at`, raw `AnalysisResult` и typed narrative-поля сохранять согласованно; при ошибке DB не должно оставаться состояния `completed` без report.
- Повторный `POST` и concurrent requests не запускают новую narrative generation для уже сохранённой v2-строки; IntegrityError path перечитывает winner row и обязательно проходит через student `_shape_response`.
- Старый [`app/prompts/report_summary.py`](/Users/yessimkhanuly13/Desktop/Profy-Backend/app/prompts/report_summary.py) и `_generate_ai_summary` удалить/перенаправить на единый narrative path, чтобы не осталось двух независимых LLM-генераторов отчёта.

## 10. Тесты и приёмка

Добавить unit/integration coverage для:

- public schema не содержит raw keys/score fields, admin schema содержит их;
- public response явно различает `interest_instrument="mi"` (8 сфер, `careers=[]`, непустые `exploration_activities`) и `interest_instrument="riasec"` (6 сфер, career tiers);
- prompt получает только valid source refs, не raw numeric blocks;
- validator отклоняет unknown refs/slugs, forbidden phrases, wrong language, invalid cardinality и новые числовые факты; третья неудача включает fallback;
- LLM disabled/error/invalid JSON и Redis unavailable всё равно возвращают 200 с валидным отчётом;
- fallback имеет 5–7 strengths и непустой `why` у каждой показанной career;
- junior/middle/senior различаются проверяемыми length/depth limits;
- interest-map thresholds/ties/flat profile отдельно для MI и RIASEC; flat RIASEC response содержит ровно 3 `worth_trying`, flat MI response не содержит careers;
- stable career ordering при одинаковом match score;
- existing stored narrative-поля не перегенерируются на GET/повторный POST;
- incomplete assessment не генерирует report и не меняет status; DB failure не оставляет completed-without-report;
- два конкурентных POST создают одну строку с одним набором narrative-полей и возвращают одинаковый stored result;
- retake удаляет v2 cache; v1 cache не читается;
- retake через question pairs и motivation pairs удаляет v2 cache, AnalysisResult, direction flow и старый goal roadmap;
- junior full flow считает MI profile/code/meta, Big Five и Harter motivation; middle использует RIASEC + Harter; senior — RIASEC + triplets;
- migration upgrade/downgrade и old row без narrative;
- admin endpoint `/api/v1/admin/assessments/{id}` сохраняет raw numbers;
- roadmap/student-context/university consumers продолжают читать полный stored top-10 raw `careers`, пока student API отдаёт максимум 5;
- OpenAPI/contract snapshot отражает breaking student response.

### 10.1 Обязательная age/retake regression matrix

Не заменять эту матрицу одним параметризованным happy-path тестом: у веток
разные instruments, таблицы ответов и failure modes.

- **Junior full flow**: MI + Big Five answers, Big Five question pairs и все
  Harter motivation pairs → completed; raw report содержит 8 MI keys,
  `careers=[]`, student v2 — 8 `interest_map` items и непустые
  `exploration_activities`. Retired junior RIASEC rows не входят в total.
- **Junior incomplete**: закрытые MI/Big Five при неполных Harter pairs не
  разрешают `/result/generate` и не меняют status на completed.
- **Middle full flow**: RIASEC + Big Five, interleaved question pairs и
  Harter motivation pairs → 6 RIASEC items, ranked careers и единые
  `motivation_highlights`.
- **Senior full flow**: RIASEC + Big Five и 12 MOST/LEAST triplets → тот же
  public motivation shape; Harter rows не учитываются в completion.
- **Retake через ordinary answers** (`assessment_service`), **question
  pairs**, **Harter motivation pairs** и **senior triplets** проверяются
  отдельными integration cases. Каждый entrypoint удаляет `AnalysisResult`,
  `report:v2:*`, direction inquiries/roadmaps и все варианты
  `roadmap:{assessment_id}:*`; следующий GET не может вернуть старый
  narrative.
- **Schema snapshots**: одна raw/admin fixture для каждого interest
  instrument и student v2 snapshots для junior/middle/senior. Student
  snapshots не содержат raw score keys, admin snapshots сохраняют их.
- **Flat/tie fixtures**: отдельно MI-flat без careers и RIASEC-flat с тремя
  `worth_trying`; одинаковый `match_score` стабильно сортируется по slug.

Ручную проверку «нет вообще никаких цифр» заменить более точной: запрещены raw numeric fields, проценты, баллы и неподанные LLM числа; возрастные/порядковые факты из разрешённого входа не являются утечкой score. Обязательно провести 8–10 ручных профилей на каждую возрастную группу, как требует §34.13, а не только 2–3.

## Отдельные обязательные follow-up tickets

- Direction taxonomy/content: сейчас top list — фактически профессии, а поля для «профессий внутри», навыков, предметов и способов попробовать пусты; без этого §18.2 п.6–7 не закрыт.
- Admin-editable/versioned prompt и strength mapping (§17.5, §18.2).
- Validation failure/admin notification, admin regeneration и email update (§17.8), если инфраструктура уведомлений не входит в этот PR.
- Background generation/status/email after tab close (§17.9), если текущий synchronous POST сохраняется.
- Полноценный flat-profile setting/admin flag, если конфигурируемый threshold не входит в первый PR.
- Миграционная инструкция для окружений, где до merge уже применялся старый university-`0034`: такие БД нельзя слепо обновлять по новой цепочке, нужен schema check + reset/reconcile.
