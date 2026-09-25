# Какие тесты есть в проекте и как формируется результат

Обзорный документ: полный каталог тестов/инструментов в коде + пошаговый разбор пути
«ребёнок зашёл → начал тест → прошёл → что он видит». Не дублирует уже существующие
доки по конкретным алгоритмам — ссылается на них там, где нужны формулы:

- [`kak-schitaetsya-rezultat.md`](./kak-schitaetsya-rezultat.md) — то же самое про
  основной (RIASEC/Big Five) результат, но простым языком, без формул, с разделом про
  правила для ИИ.
- [`senior-report-algorithm.md`](./senior-report-algorithm.md) — технический разбор с
  формулами и порогами для старшей/средней группы.
- [`psychologist-review-gate-plan.md`](./psychologist-review-gate-plan.md) — детали
  гейта «психолог должен опубликовать отчёт».
- [`roadmap-content-generation.md`](./roadmap-content-generation.md) — генерация
  персонального плана (roadmap) после отчёта.
- [`psych-block-contract.md`](./psych-block-contract.md) — контракт психологического
  блока (Belbin/ASTUR/Eysenck и т.д.), специалист-только раздел.

---

## 1. Два разных слоя тестов в проекте

Это ключевое, что нужно понимать: в кодовой базе есть **два непересекающихся набора
тестов**, которые ребёнок проходит по-разному и результаты которых видят разные люди.

| | Основная батарея | Специализированный (психологический) блок |
|---|---|---|
| Кто проходит | **Каждый** ребёнок, без исключений, в рамках одного `Assessment` | Только те, кому психолог явно назначил блок (Belbin/АСТУР), либо кто сам прошёл самостоятельный экран (психоэмоциональный тест) |
| Кто видит результат | Сам ребёнок (`GET /result/{id}`) | **Только психолог/админ** (`report_service.psych_sections_for` — жёстко проверяется по роли, не по согласию) |
| Где отчёт | `ResultResponseV2` (student-facing) | `NewTestsSections` / психологические секции `ValiditySection`/`PsychoEmotionalSection` в отчёте психолога |
| Зачем | Интересы, характер, мотивация → карьерные направления | Углублённая психодиагностика для специалиста (темперамент, тревожность, командная роль, интеллект, эмпатия, достоверность протокола) |

---

## 2. Каталог тестов (инструментов)

### 2.1 Основная батарея — обязательна для всех, входит в один `Assessment`

| Инструмент | Что измеряет | Возраст | Формат | Кол-во пунктов | Контент | Скоринг |
|---|---|---|---|---|---|---|
| **RIASEC** (Holland) | 6 категорий интересов R/I/A/S/E/C | middle, senior (junior — см. MI ниже) | Likert 1–5 | 146 (junior 38 + middle 36 + senior 72, кумулятивно) | `scripts/riasec_question_bank.py` | `app/services/riasec_service.py` |
| **MI** (Multiple Intelligences) | 8 категорий способностей (verbal/logical/musical/visual/bodily/interpersonal/intrapersonal/naturalistic) — замена RIASEC для младших | **только junior** (6–9 лет) | Likert 1–5 | 48 | `scripts/mi_question_bank.py` | `app/services/mi_service.py` |
| **Big Five** (IPIP-NEO-120) | 5 черт характера (N/E/O/A/C) + фасеты → «Твой характер», стиль мышления | все три группы, один и тот же тест | Likert 1–5 | 120 (junior 30 + middle 30 + senior 60) | `scripts/bigfive_question_bank.py` | `app/services/bigfive_service.py` |
| **Мотивация (триады)** | 9 категорий (interest/challenge/helping/freedom/money/recognition/stability/creation/teamwork) | **только senior** | Форс-чойс MOST/LEAST в тройках | 36 утверждений | `scripts/motivation_statement_bank.py` | `app/services/motivation_service.py` |
| **Мотивация (пары)** | те же 9 категорий, формат Хартера | junior, middle | Форс-чойс пары «что ближе» | 18 пар | `scripts/motivation_pair_bank.py` | `app/services/motivation_pair_service.py` |
| **Дилеммы (question_pairs)** | те же RIASEC/Big Five пункты, но в формате «выбери А или Б» вместо Likert-шкалы | junior (свой отдельный экран `/assessment/pairs`), middle (вплетены в общий Likert-экран) | Форс-чойс пары | 67 (junior 19+15, middle 18+15) | `scripts/question_pairing.py` | `app/services/question_pair_service.py` — выбор пишется как 2 обычных `UserResponse` (5 и 1), дальше считается как обычный Likert-ответ |
| **Protocol validity** («шкала лжи») | MC-SDS социальная желательность + infrequency-ловушки (вопросы-«капканы») — не личностная черта, а достоверность самого прохождения | вмешана в senior/middle Likert-блок RIASEC, не видна отдельным экраном | Likert 1–5, замаскирован под RIASEC (`instrument='riasec'` на проводе) | переменно, по банку | `scripts/lie_scale_bank.py` (сид: `scripts/seed_lie_scale_questions.py`) | `app/services/validity_service.py` — **результат этого теста ребёнку никогда не показывается**, только психологу (`ValiditySection`) |

Правило видимости по возрасту — `app/services/age_tiers.py`: короткий тест это **префикс**
длинного, не отдельный набор — `junior ⊆ middle ⊆ senior`. Т.е. вопросы, помеченные
`age_tier=junior`, видят все три группы; `age_tier=middle` — middle и senior;
`age_tier=senior` — только senior.

**Состояние в этой локальной БД прямо сейчас** (после прогона стандартного CD-пайплайна
сидов): RIASEC/Big Five/MI/question_pairs/мотивация — засеяны. `validity` — **пусто**
(его сид-скрипт не входит в список seed-шагов `cd.yml`/`cd-dev.yml`, см. §5).

### 2.2 Специализированный (психологический) блок — НЕ основная батарея

Эпик PRO-282/PRO-338. Ключевая деталь: файл `app/services/new_tests_report_service.py`
прямо говорит в докстринге — «never by the student-facing `/result`». Ребёнок эти
результаты не видит вообще, ни в каком виде.

| Инструмент | Методика | Формат | Кол-во | Как назначается | Скоринг |
|---|---|---|---|---|---|
| **Профессиональные типы (ДДО)** | Климов + Йовайши/Резапкина, 5 шкал (Ч-П/Ч-Т/Ч-Ч/Ч-З/Ч-Х) | 20 форс-чойс пар (`instrument=professional_types`) | 20 пар | часть общего Likert-потока (не gated психологом) | `professional_types_service.py` |
| **Способности (ДДО)** | тот же Климов, самооценка по тем же 5 шкалам | Likert | 5 пунктов | вместе с ДДО-интересами | `professional_types_service.py` |
| **Айзенк (EPI)** | темперамент | Да/Нет | 57 | часть Likert-потока | `eysenck_service.py` |
| **Элерс** | уровень притязаний/мотивация достижения | Да/Нет | — | часть Likert-потока | `elers_service.py` |
| **Бойко** | эмпатические способности, 6 каналов | Да/Нет | 36 | часть Likert-потока | `boyko_empathy_service.py` |
| **Кондаш/Прихожан** | шкала тревожности, 4 субшкалы | 5-балльная (Нет…Очень) | 40 | часть Likert-потока | `kondash_anxiety_service.py` |
| **Белбин (BTRSPI)** | командные роли (для 18+, методическая оговорка для школьников) | своя анкета, один сабмит | 7 блоков | **психолог явно назначает** (`POST /psychologist/.../assign-extended-block`) | `belbin_service.py` |
| **АСТУР** | интеллект, школьный тест умственного развития | подтесты, таймер на каждый | по подтестам | **психолог явно назначает** | `astur_service.py` / `astur_scoring.py` |
| **Психоэмоциональный тест (МЦВ Собчик)** | цветовой выбор, тревога/компенсация/вегетативный тонус | выбор 8 цветов дважды (список 1 и 2) | 2×8 цветов | ребёнок проходит сам, отдельный экран `/assessment/psychoemotional/start` + `/finish` | `app/services/psychoemotional/` (`scoring.py`, `engine.py`) |

Belbin и АСТУР — единственные два теста в проекте, у которых контент **не** живёт в
таблице `questions` вообще: `scripts/belbin_bank.py`/`scripts/astur_bank.py` отдаются
напрямую по запросу (`GET /assessment/belbin/content`, `GET /assessment/astur/content`),
без сид-скрипта и без строк в БД — поэтому для них вопрос «засеяно или нет» не
применим, в отличие от всех остальных инструментов в этой таблице.

Названия «Люшер» в продукте намеренно не используется (см. докстринг
`PsychoEmotionalSection` в `app/schemas/result_v2.py`) — только «психоэмоциональный тест».

**Важная находка при подготовке этого документа:** у ДДО/Eysenck/Elers/Boyko/Kondash/
validity есть полноценные `scripts/seed_*.py`, но ни один из них **не входит** в список
шагов `.github/workflows/cd.yml`/`cd-dev.yml` (сверено построчным grep — там только 8
сидов основной батареи + `build_universities.py`, см. раздел Content pipeline в
`CLAUDE.md`). Это значит, что на свежей БД (и, скорее всего, на текущих prod/dev, если
это руками никто не гонял) вопросы этого блока **не существуют** физически, а не просто
"не пройдены". Проверено локально прямо сейчас:

```sql
SELECT instrument, count(*) FROM questions GROUP BY instrument;
--  riasec | big_five | mi   →  есть
--  validity / professional_types_abilities / eysenck / elers /
--  boyko_empathy / kondash_anxiety  →  0 строк
```

Если специализированный блок реально нужен для теста/демо — сиды такие:
`scripts/seed_professional_types_questions.py`, `scripts/seed_eysenck_questions.py`,
`scripts/seed_elers_questions.py`, `scripts/seed_boyko_empathy_questions.py`,
`scripts/seed_kondash_anxiety_questions.py`, `scripts/seed_lie_scale_questions.py`
(validity). Belbin/АСТУР сеять не нужно — их контент не лежит в `questions` вообще, см.
сноску в §2.2 выше. Чинить пайплайн — не задача этого документа, здесь только
зафиксирован факт, на который стоит обратить внимание отдельно.

---

## 3. Поток: ребёнок заходит → начинает тест → проходит → результат

Пошагово, только основная батарея (специализированный блок — отдельный, опциональный
довесок, см. §2.2).

1. **Регистрация/логин** — `POST /api/v1/auth/register` или `/login`. Роль всегда
   `student` для самостоятельной регистрации.
2. **Профиль** (`Profile`) — возраст, класс, город, что нравится/не нравится в школе.
   Отсюда высчитывается `age_group` (`compute_age_group`, `app/models/profile.py`) —
   junior/middle/senior. Это единственное, что решает, КАКИЕ вопросы увидит именно этот
   ребёнок (§2.1 таблица + `age_tiers.py`).
3. **`POST /assessment/start`** с `goal` (`explore` / `profession` / `university` /
   `unsure`) — создаёт `Assessment(status=in_progress)`. Один активный `Assessment` на
   профиль: если уже есть незавершённый — он удаляется (каскадом чистит все ответы) и
   создаётся заново, а не переиспользуется (`assessment_service.create_assessment`).
   - junior разрешена только цель `explore`.
   - middle не может выбрать `university` (только для senior).
4. **Вопросы** — `GET /assessment/questions` (Likert-блок: RIASEC/Big Five/MI вперемешку
   с невидимыми validity-пунктами) и, для junior (отдельный экран) / middle (вплетено в
   тот же экран), forced-choice дилеммы `GET /assessment/pairs`.
5. **Ответы** — `POST /assessment/{id}/answers` пачками, по мере прохождения (не всё
   сразу). Хранится как `UserResponse(question_id, answer_value 1..5)`. Повторная отправка
   того же вопроса перезаписывает значение (upsert по `(assessment_id, question_id)`).
6. **Мотивация** — отдельный шаг после (или параллельно) Likert-блока: тройки MOST/LEAST
   (senior) или пары (junior/middle). Тест считается завершённым **только когда обе фазы
   закрыты** — и весь Likert, и вся мотивация (`assessment.status` флипается в
   `completed` внутри `motivation_service.submit_motivation_answers`, не в
   `submit_answers`).
7. **`POST /result/generate`** — точка входа в сборку отчёта
   (`report_service.build_report`). Правила:
   - Гейт полноты (`_assert_assessment_complete`) — если тест не полностью пройден,
     собрать отчёт нельзя.
   - Кэш в Redis на 24 часа, `pg_advisory_xact_lock` защищает от гонки двух параллельных
     запросов на генерацию одного и того же отчёта.
   - Текст (summary, карточки) пишет ИИ (если включён и прошёл валидацию) либо
     детерминированный шаблон — см. `kak-schitaetsya-rezultat.md` §4 для точных правил,
     что ИИ можно и нельзя писать.
   - Сохраняется как `AnalysisResult(review_status=pending_review)` — **не публикуется
     сразу**, см. §6.
8. **Ожидание публикации.** Пока `review_status != published`, и `POST /result/generate`,
   и `GET /result/{id}` отдают ребёнку не отчёт, а
   `{"status": "pending_review", "assessment_id": ...}` (200, не 403/404 — фронт уже
   умеет отличать это состояние). Психолог получает письмо о новом отчёте на проверку,
   заходит в `GET /psychologist/reviews` → открывает → может отредактировать текст
   (`PATCH .../result/{id}`) → публикует (`POST .../result/{id}/publish`). Полные детали
   гейта — `psychologist-review-gate-plan.md`.
9. **`GET /result/{id}`** после публикации — уже отдаёт полный отчёт (см. §4).
10. Дальше — необязательные шаги: цель → `GET /result/{id}/goal-context` (блок «Фокус
    под твою цель»), направление → AI-опрос `direction_inquiry`, план →
    `roadmap_builder` (см. `roadmap-content-generation.md`).

---

## 4. Что именно приходит ребёнку в `/result/{id}` (после публикации)

Схема — `app/schemas/result_v2.py`, дискриминированная по `interest_instrument`
(`"mi"` для junior или `"riasec"` для middle/senior — разные обязательные поля).

Общее для обеих веток (`_ResultResponseBase`):

| Поле | Что это |
|---|---|
| `summary` | Общее резюме отчёта (ИИ или шаблон) |
| `strength_cards` | Карточки сильных сторон (заголовок + описание) |
| `interest_map` | Все 6 RIASEC-сфер (или 8 MI-категорий) с уровнем low/medium/high — **все**, включая слабые, в отличие от `strength_cards` |
| `interest_map_note` | 1-2 предложения о карте интересов (детерминировано, без ИИ) |
| `thinking_style_notes` | Стиль мышления (до 4 категорий: creative/systematic/strategic/practical) |
| `personality_notes` | Ровно 5 карточек «Твой характер», по одной на черту Big Five, с уровнем low/medium/high **относительно 4 других черт этого же ребёнка**, не абсолютной шкалы |
| `personality_note` | Синтез поверх 5 карточек характера |
| `motivation_highlights` | Топ-3 категории мотивации, готовыми фразами |
| `is_flat_profile` | true если разброс между самой сильной и самой слабой RIASEC/MI категорией `< 25` — список профессий **не укорачивается**, просто честный дисклеймер в тексте |
| `exploration_note` | Закрывающая фраза-приглашение (актуальна для junior) |
| `final_analysis` | Финальный вывод, последним на странице |
| `validity`, `psychoemotional` | **Всегда `null` для ребёнка** — эти два поля существуют в схеме только потому что психолог получает тот же объект отчёта с досыпанными секциями; `report_service.psych_sections_for` жёстко не даёт им заполниться для роли `student` |
| `disclaimer` | Фиксированная фраза «Это не окончательный выбор, а карта возможных направлений…» — вшита в код, ИИ её никогда не пишет и не может убрать |

**MI-ветка (junior, `interest_instrument="mi"`):**
- `careers` — всегда пустой список (запрещено на уровне схемы, `max_length=0`) — про
  профессии младшей группе не говорят вообще.
- `exploration_activities` — список активностей «что можно попробовать» вместо профессий.

**RIASEC-ветка (middle/senior, `interest_instrument="riasec"`):**
- `careers` — до 10 профессий, с `rank` (1..10), `tier` (`strong` / `good` /
  `worth_trying`), текстом «почему подходит» (`why`, никогда не пустой) и «что
  попробовать прямо сейчас» (`try_now`). Подбор — Pearson-корреляция полного 6-мерного
  профиля vs `onet_vector` направления, подробности в `senior-report-algorithm.md` §2.
- `interest_combination` — как сочетаются 2 самых выраженных типа на гексагоне Голланда
  (`adjacent`/`alternate`/`opposite`), `null` если второй тип не дотягивает до «medium».

---

## 5. Файлы-справочник

| Что | Файл |
|---|---|
| Точка входа в основной поток | `app/routers/assessment.py`, `app/routers/result.py` |
| Оркестрация сборки отчёта | `app/services/report_service.py` |
| RIASEC / подбор профессий | `app/services/riasec_service.py` |
| MI (junior) | `app/services/mi_service.py` |
| Big Five | `app/services/bigfive_service.py` |
| Мотивация (senior / junior-middle) | `app/services/motivation_service.py`, `app/services/motivation_pair_service.py` |
| Дилеммы (forced-choice pairs) | `app/services/question_pair_service.py` |
| Возрастная видимость вопросов | `app/services/age_tiers.py` |
| Итоговая схема ответа студенту | `app/schemas/result_v2.py` |
| Психологический блок — оркестрация специалист-отчёта | `app/services/new_tests_report_service.py` |
| Психологический блок — назначение Belbin/АСТУР | `app/services/extended_block_service.py` |
| Психоэмоциональный тест | `app/services/psychoemotional/` |
| Согласие на психоблок | `app/services/consent_service.py` |
| Review-gate (психолог публикует) | `app/routers/psychologist.py`, `docs/psychologist-review-gate-plan.md` |
| Полный список сид-скриптов, гоняемых на деплое | `.github/workflows/cd.yml` (см. также `CLAUDE.md`, Content pipeline) |
