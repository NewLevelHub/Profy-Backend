# План: сводный эндпоинт «все баллы по всем тестам» для психолога

Проектный документ (design plan), код не реализован — это дизайн будущего эндпоинта:
путь, схема ответа, откуда берутся данные, известные пробелы, пример ответа. Смотри
также [`tests-catalog-and-result-flow.md`](./tests-catalog-and-result-flow.md) (каталог
всех тестов проекта) и [`psych-block-contract.md`](./psych-block-contract.md)
(контракт психологического блока) — этот документ на них опирается, не дублирует.

---

## 1. Зачем это нужно

Сегодня психолог, чтобы собрать полную картину по одному прохождению ученика, обязан
дёргать минимум 4 разных эндпоинта:

1. `GET /psychologist/students/{id}` — профиль/артефакты/список assessment'ов.
2. `GET /psychologist/students/{id}/assessments/{assessment_id}/report` — самый полный
   на сегодня: `{report: ResultV2Schema, new_tests: NewTestsSections, ai_analysis}`.
3. `GET /psychologist/students/{id}/results/{assessment_id}` (**results**, множественное
   число — отдельный от п.2 путь) — статус ревью/публикации + редактируемые поля отчёта.
4. `GET /psychologist/students/{id}/notes` — заметки психолога.

И даже пункт 2, самый полный, **не содержит сырых баллов** по основной батарее
(RIASEC/Big Five/MI/мотивация) — он переиспользует `ResultV2Schema`, ту же схему, что
видит сам ученик, а её докстринг прямо говорит: «no percentages, no match_score, no raw
category letters/keys outside of `interest_map[].code`». Психолог видит `level:
low/medium/high`, а не «R: 62.4%». Есть отдельная `AdminAnalysisResultResponse` с сырыми
числами, но она (а) недоступна психологу, только admin-эндпоинтам, и (б) не содержит
новых JSONB-контейнеров (`validity`/`psychoemotional`/`professional_types`/`eysenck`/
`elers`/`empathy_confidence`/`psych_ai_analysis`) — схема писалась до их появления.

Плюс отдельный пробел: **статус назначения Belbin/АСТУР** («назначено, но не пройдено»
vs «не назначено вообще») психологу сегодня **вообще не виден** ни одним эндпоинтом —
единственный GET на это (`GET /assessment/{id}/extended-blocks`) — student-owner-only,
403 для психолога.

Цель — один эндпоинт, который отдаёт психологу **сырые баллы буквально по всем тестам**
— и по тем, что видит ученик (с реальными числами, не «high/medium/low»), и по тем
специализированным, что ученик не видит никогда, — плюс статус прохождения/назначения
каждого теста, в одном ответе.

---

## 2. Эндпоинт

```
GET /api/v1/psychologist/students/{student_id}/assessments/{assessment_id}/scores
```

- Роутер: `app/routers/psychologist.py`, рядом с существующим `.../report`
  (тот же префикс пути, тот же стиль).
- Auth: `_require_psychologist_or_admin` + `_require_assigned_student` — тот же паттерн,
  что уже используют `.../report` и `.../results/{assessment_id}` (никакой новой
  авторизационной логики, переиспользуется существующая зависимость).
- Только чтение, ничего не пишет и не считает заново то, что уже посчитано и
  закэшировано — те же источники данных, что использует `new_tests_report_service.py`
  и `report_service.py` сегодня (см. таблицу переиспользования, §4).

---

## 3. Схема ответа

Новые Pydantic-модели, `app/schemas/psychologist_scores.py`. Пять верхнеуровневых
секций:

```
PsychologistFullScoresResponse
├── meta: ScoresMeta                         # кто, когда, статус ревью
├── core: CoreInstrumentsScores              # то, что видит ученик — но сырыми числами
├── specialist: SpecialistInstrumentsScores  # то, что ученик не видит никогда
├── extended_blocks: list[ExtendedBlockStatus]  # назначено/пройдено — Belbin, АСТУР
└── psychoemotional: PsychoEmotionalRawScores | None
```

### `ScoresMeta`

`assessment_id`, `student_id`, `age_group`, `goal`, `review_status`
(`pending_review`/`published`), `reviewed_by`/`reviewed_at`, `published_by`/
`published_at`, `report_generated_at` — переиспользует поля, уже существующие в
`PsychologistResultDetailResponse` (просто вынесены сюда же, чтобы не дёргать
3-й эндпоинт отдельно).

### `CoreInstrumentsScores`

По одному под-объекту на инструмент, `null` если ученик этой возрастной группы его не
проходит:

| Под-объект | Поля | Источник (существующая функция, без изменений) |
|---|---|---|
| `riasec` | `raw: dict[str,int]`, `normalized: dict[str,float]`, `differentiation: float`, `consistency: str`, `top_code: list[str]`, `strengths: list[str]`, `weaknesses: list[str]`, `aversion: dict[str,int]` | `riasec_service.raw_scores/normalize/differentiation/consistency/top_code/strengths_weaknesses/aversion` |
| `mi` | то же самое, категории MI вместо RIASEC (только junior) | `mi_service.*` (зеркальный API) |
| `big_five` | `raw: dict[str,float]`, `normalized: dict[str,float]`, `facets: dict[str, dict[str,dict]]` (raw+normalized по фасетам на домен), `personality_profile: dict[str,float]` (5 черт, N инвертирован) | `bigfive_service.raw_scores/normalize/facet_raw/facet_normalize`, `bigfive_content.build_personality_profile` |
| `thinking_style` | `{creative_think, systematic, strategic, practical}` (0-100 каждое) | `thinking_style_service.compute` |
| `motivation` | `raw: dict[str,int]` (9 категорий), `top: list[str]` | `motivation_service.raw_scores/top_categories` (senior) или `motivation_pair_service.raw_scores` + `motivation_service.top_categories` (junior/middle — `motivation_pair_service` не имеет своей `top_categories`, переиспользует чужую с тем же `CATEGORY_ORDER`) |
| `careers` | `list[{slug, name, match_score, tier}]`, до 10, с **реальным** Pearson r / legacy-score, не только rank/tier как в `ResultResponseV2.careers` | `riasec_service.matched_careers` (уже считает `(Direction, score)`, просто сегодня score никуда не прокидывается психологу) |

### `SpecialistInstrumentsScores`

По одному под-объекту на инструмент, каждый `null`, если тест не был предъявлен/не
отвечен (используется уже существующая в коде конвенция «`None` = не проходил», а не
нулевой словарь — этот паттерн последовательно выдержан во всех `*_service.py`
спец-блока):

| Под-объект | Поля | Источник |
|---|---|---|
| `validity` | `sd_raw, sd_level, sd_bounds, longstring_max, irv, infrequency_failed, careless_flag, traffic_light, thresholds_version` | то же, что уже собирает `report_service._build_validity_section` (переиспользуется, без ужатия под `ValiditySection`) |
| `professional_types` | `interest_scores: dict[str,int]`, `abilities_scores: dict[str,int]`, `hybrid_profile: list[str] \| None` | `professional_types_service.interest_raw_scores/abilities_raw_scores/hybrid_profile` |
| `eysenck` | `extraversion_raw, neuroticism_raw, lie_scale_raw, quadrant` | `eysenck_service.raw_scores/quadrant` |
| `elers` | `score` | `elers_service.raw_score` |
| `boyko_empathy` | `channels: dict[str,int]` (6 каналов), `total: int` | `boyko_empathy_service.raw_scores` |
| `kondash_anxiety` | `interpersonal_raw: int` — **только эта подшкала**; `school/self_esteem/magical: null` | `kondash_anxiety_service.interpersonal_raw_score` — см. §5, известный пробел: остальные 3 подшкалы физически нечем посчитать (функций нет) |
| `belbin` | `role_totals: dict[str,int]` (8 ролей, сырые), `ranked_roles`, `dominant_role` | `belbin_service.get_latest_run` → `.role_totals`, `belbin_service.interpret_role_totals` |
| `astur` | `subtest_scores: dict[str,int]`, `raw_score: int`, `spn_group`, `recommended_profile`, `lability_first_half_accuracy`, `lability_second_half_accuracy` | `astur_service.get_latest_run` → `astur_scoring.score_run(run.answers, run.lability_answers, ...)` — уже вызывается именно так внутри `new_tests_report_service._build_intelligence_section`, тот же вызов переиспользуется |

### `extended_blocks: list[ExtendedBlockStatus]`

**Новая для психолога видимость**, которой сегодня нет ни в одном доступном ему
эндпоинте:

```
{block: "belbin" | "astur", assigned_at: datetime, completed: bool}
```

Источник — уже существующая функция `extended_block_service.list_assignments(
assessment_id, db)` (сегодня используется только за student-owner-only роутом,
`app/routers/extended_blocks.py`). Никакой новой скоринг-логики не требуется — только
вызвать уже существующую функцию из нового психологического роута.

### `PsychoEmotionalRawScores`

Сырые индексы психоэмоционального теста (тревога, компенсация, SO, VK, D,
split/positional pairs) — то же, что уже собирает
`report_service._build_psychoemotional_section`, без ужатия под публичную
`PsychoEmotionalSection` (там уже почти всё сырое, просто выносится в новую секцию
рядом с остальными сырыми баллами вместо вложенности в `report.psychoemotional`).

---

## 4. Переиспользование — никакой новой скоринг-математики

Всё выше — **сборка** уже существующих чистых функций, без дублирования формул.
Единственное действительно новое — сама функция-оркестратор (по аналогии с
`new_tests_report_service.build_new_tests_sections`, которая уже делает ровно это для 6
секций спец-блока: try/except на каждую секцию отдельно, чтобы падение одного
инструмента не роняло остальные) плюс проброс `extended_block_service.
list_assignments` в психологический роут.

---

## 5. Известные пробелы — фиксируются, не чинятся в рамках этого плана

- **Kondash/Прихожан**: банк вопросов содержит 4 подшкалы (`school`, `self_esteem`,
  `interpersonal`, `magical`), но в коде есть скоринг только для `interpersonal`
  (`kondash_anxiety_service.interpersonal_raw_score`). Остальные 3 в ответе будут
  `null` — это не баг сборки, а отсутствие скоринг-функций в самом сервисе. Если нужно
  закрыть — отдельная задача на `kondash_anxiety_service.py`, не на этот эндпоинт.
- **АСТУР**: `astur_scoring.score_run` считается «на лету» при каждом запросе (не
  кэшируется на строке `AsturRun`) — так же ведёт себя уже существующий
  `new_tests_report_service._build_intelligence_section`; новый эндпоинт просто
  повторяет тот же вызов, поведение не меняется.
- **`AdminAnalysisResultResponse`** (роль admin) не трогается и не расширяется этим
  планом — параллельная, отдельная поверхность.

---

## 6. Пример ответа

```json
{
  "meta": {
    "assessment_id": "b6b6a1b0-2f3a-4a3e-9b7a-2d0b7c9e1a10",
    "student_id": "47dce7c7-b38a-40b8-8bd7-ec41fa8d5001",
    "age_group": "senior",
    "goal": "profession",
    "review_status": "published",
    "reviewed_by": "0a1b2c3d-0000-0000-0000-000000000001",
    "reviewed_at": "2026-09-18T09:12:00Z",
    "published_by": "0a1b2c3d-0000-0000-0000-000000000001",
    "published_at": "2026-09-18T09:14:00Z",
    "report_generated_at": "2026-09-18T08:55:00Z"
  },
  "core": {
    "riasec": {
      "raw": {"R": 18, "I": 34, "A": 31, "S": 22, "E": 15, "C": 19},
      "normalized": {"R": 30.0, "I": 56.7, "A": 51.7, "S": 36.7, "E": 25.0, "C": 31.7},
      "differentiation": 31.7,
      "consistency": "medium",
      "top_code": ["I", "A", "S"],
      "strengths": ["I", "A"],
      "weaknesses": ["E"],
      "aversion": {"R": 1, "I": 0, "A": 0, "S": 0, "E": 3, "C": 1}
    },
    "mi": null,
    "big_five": {
      "raw": {"N": 41.2, "E": 55.0, "O": 68.4, "A": 49.1, "C": 60.3},
      "normalized": {"N": 34.3, "E": 45.8, "O": 57.0, "A": 40.9, "C": 50.3},
      "facets": {
        "O": {
          "1": {"raw": 12.1, "normalized": 60.5},
          "2": {"raw": 10.8, "normalized": 54.0}
        },
        "C": {
          "1": {"raw": 9.5, "normalized": 47.5},
          "2": {"raw": 11.0, "normalized": 55.0},
          "4": {"raw": 10.2, "normalized": 51.0}
        }
      },
      "personality_profile": {
        "openness": 57.0,
        "conscientiousness": 50.3,
        "extraversion": 45.8,
        "agreeableness": 40.9,
        "emotional_stability": 65.7
      }
    },
    "thinking_style": {
      "creative_think": 57.3,
      "systematic": 55.0,
      "strategic": 51.0,
      "practical": 47.5
    },
    "motivation": {
      "raw": {
        "interest": 14, "challenge": 9, "helping": 11, "freedom": 7, "money": 5,
        "recognition": 8, "stability": 6, "creation": 10, "teamwork": 9
      },
      "top": ["interest", "creation", "helping"]
    },
    "careers": [
      {"slug": "psychologist", "name": "Психолог", "match_score": 0.87, "tier": "strong"},
      {"slug": "designer", "name": "Дизайнер", "match_score": 0.79, "tier": "good"},
      {"slug": "teacher", "name": "Педагог", "match_score": 0.74, "tier": "good"}
    ]
  },
  "specialist": {
    "validity": {
      "sd_raw": 6,
      "sd_level": "ok",
      "sd_bounds": [8, 15],
      "longstring_max": 4,
      "irv": 0.42,
      "infrequency_failed": 0,
      "careless_flag": false,
      "traffic_light": "green",
      "thresholds_version": 2
    },
    "professional_types": {
      "interest_scores": {"practical": 3, "technical": 2, "social": 8, "sign": 4, "artistic": 3},
      "abilities_scores": {"practical": 1, "technical": 0, "social": 3, "sign": 2, "artistic": 2},
      "hybrid_profile": null
    },
    "eysenck": {
      "extraversion_raw": 15,
      "neuroticism_raw": 11,
      "lie_scale_raw": 3,
      "quadrant": "sanguine"
    },
    "elers": {"score": 17},
    "boyko_empathy": {
      "channels": {
        "rational": 4, "emotional": 5, "intuitive": 3,
        "attitudes": 4, "penetration": 3, "identification": 5
      },
      "total": 24
    },
    "kondash_anxiety": {
      "interpersonal_raw": 18,
      "school": null,
      "self_esteem": null,
      "magical": null,
      "_note": "school/self_esteem/magical: скоринг не реализован в kondash_anxiety_service.py"
    },
    "belbin": null,
    "astur": null
  },
  "extended_blocks": [
    {"block": "astur", "assigned_at": "2026-09-17T10:00:00Z", "completed": false}
  ],
  "psychoemotional": {
    "run_number": 1,
    "completed_at": "2026-09-16T14:20:00Z",
    "choice_1": [3, 5, 1, 6, 2, 4, 0, 7],
    "choice_2": [3, 1, 5, 6, 2, 0, 4, 7],
    "d_value": 8,
    "anxiety": {"score": 3, "level": "moderate", "breakdown": {"0": 1, "2": 2}},
    "compensation": {
      "score": 2, "level": "low", "breakdown": {"1": 2},
      "purple_forward": false, "purple_position": 5
    },
    "so_value": 14,
    "so_level": "norm",
    "vk_value": 1.4,
    "vk_level": "balance",
    "black_first": false
  }
}
```

`belbin: null` — не назначен. `astur` в `specialist` тоже `null`, т.к. ещё не пройден,
хотя уже назначен — статус назначения виден отдельно в `extended_blocks`. Это и есть
разница между «не назначено» и «назначено, но не готово», которой сегодня нет ни в
одном психологу доступном эндпоинте.

---

## 7. Файлы-справочник для будущей реализации

| Что | Файл |
|---|---|
| Новый роут | `app/routers/psychologist.py` |
| Новые схемы ответа | `app/schemas/psychologist_scores.py` (новый файл) |
| Оркестратор сборки | новый `app/services/psychologist_scores_service.py`, по образцу `new_tests_report_service.py` (try/except на секцию) |
| RIASEC/Big Five/MI/мотивация/careers сырые баллы | `riasec_service.py`, `bigfive_service.py`, `mi_service.py`, `motivation_service.py`, `motivation_pair_service.py`, `thinking_style_service.py` |
| Спец-блок сырые баллы | `professional_types_service.py`, `eysenck_service.py`, `elers_service.py`, `boyko_empathy_service.py`, `kondash_anxiety_service.py`, `belbin_service.py`, `astur_service.py`+`astur_scoring.py` |
| Validity / психоэмоциональный | `validity_service.py`, `app/services/psychoemotional/` |
| Статус назначения Belbin/АСТУР | `extended_block_service.list_assignments` (уже существует, только пробросить) |
| Авторизация | `_require_psychologist_or_admin`, `_require_assigned_student` (уже существуют в `psychologist.py`) |
