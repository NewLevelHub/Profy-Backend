# Roadmap goal contract

Scope: tasks #2–#8, #11–#14 from `docs/riasec-roadmap-tasks.md` (Block A).
Author: Backend Architect sessions, `pro-156`.

Status: **complete**. Tasks #2 and #4 were open product/architecture decisions
in an earlier draft of this doc; both have since been resolved by the project
owner (see §3/§4) and are implemented and tested on `pro-156` as of this
revision. This is the reference for the frontend team — it describes the
final response shapes, not a work-in-progress.

**Update (2026-08-04): tasks #1/#9/#10 are now also shipped.** This doc
originally described the schema only, ahead of the goal-specific content
generators (explore auto-selection, profession expansion) landing. They have
since landed on top of this same schema, with no shape changes — see §8 for
what changed and where.

---

## 1. What's shipped

### 1.1 `POST /api/v1/roadmap/directions` — 0..N directions [TASK #8]

Replaces the old `POST /api/v1/roadmap/direction` (exactly one `direction_slug`
in the body). New shape:

```json
POST /api/v1/roadmap/directions
{
  "assessment_id": "5c1e6c0a-...-...",
  "direction_slugs": ["architect"]
}
```

Response is now a **list**, one entry per requested slug, in request order.
See §2 for the full, current response shape (this replaces the earlier
draft's abbreviated example — it now includes `stages` and the finalized
`university_requirements` fields from §4).

Notes:
- `admission_requirements`/`admission_summary` are always `[]`/`""` today —
  **pre-existing**, not something this task introduced. `Program.requirements`
  never actually contains those two keys in the live dev DB (0/1483 rows,
  see §5). The code has read them since before this task; nobody's supplied
  that data yet.
- An **empty** `direction_slugs` list, for `goal in (explore, unsure)`
  **only**, now resolves to the top 3 leaf directions by
  `AssessmentSession.belief` [TASK #1/#9 — see §8] instead of 400ing. For
  every other goal (`profession`/`university`/`known`), or for an
  explore/unsure assessment with no belief signal yet (no `AssessmentSession`
  or empty `belief`), it still 400s — see `roadmap_builder.
  _resolve_explore_direction_slugs`.
- `GET /api/v1/roadmap/{assessment_id}/directions/{slug}` (single, unchanged)
  and `GET /api/v1/roadmap/{assessment_id}/directions` (list, all stored
  roadmaps for the assessment) both still work.

### 1.2 Explore-goal access gate relaxed [TASK #7]

`goal in (explore, unsure)` no longer requires `Assessment.
selected_direction_slug` to be set before generating a plan for a specific
direction — explore/unsure students are trying directions on, not
committing. profession/university/known are unchanged (still 400 without a
confirmed direction). Generating a plan under explore/unsure also no longer
writes `selected_direction_slug` — trying a direction must not silently
"confirm" it. See `app/services/roadmap_builder.py`,
`_require_direction_roadmap_access` and `generate_direction_roadmap`.

### 1.3 `Program.deadlines` / `Program.grants` wired into `university_requirements` [TASK #11]

Fields on `UniversityRequirement`: `application_deadline: str | None` and
`grants: list[ProgramGrant]`. Backend-populated, no LLM. See §5 for current
fill rates.

### 1.4 Horizon skeleton, now wired into storage and responses [TASK #12 / #6]

`app/schemas/roadmap.py` exposes the 5-horizon container:

```python
Horizon.month_1          # "Ближайший месяц"
Horizon.months_3         # "Ближайшие 3 месяца"
Horizon.months_6         # "Ближайшие 6 месяцев"
Horizon.months_12        # "12 месяцев"
Horizon.until_admission  # "До поступления"

build_empty_horizon_milestones() -> list[RoadmapMilestone]
```

As of this revision it is **wired end-to-end**: `DirectionRoadmap.stages`
(new JSONB column, migration `0041_add_stages_to_direction_roadmap.py`)
stores it, `DirectionRoadmapResponse.stages` returns it. Every
(re)generated plan currently gets the 5-entry skeleton with empty `tasks`
lists — no generator (#9/#10) fills `.tasks` in yet, so `stages` is
present and correctly shaped, just not yet content-bearing:

```json
"stages": [
  { "horizon": "month_1", "title": "Ближайший месяц", "tasks": [] },
  { "horizon": "months_3", "title": "Ближайшие 3 месяца", "tasks": [] },
  { "horizon": "months_6", "title": "Ближайшие 6 месяцев", "tasks": [] },
  { "horizon": "months_12", "title": "12 месяцев", "tasks": [] },
  { "horizon": "until_admission", "title": "До поступления", "tasks": [] }
]
```

Frontend implication: **build the horizon-rendering UI now** against this
shape — it will not change when #9/#10 land, only `tasks` will stop being
empty.

---

## 2. `DirectionRoadmapResponse` — full current shape

This is the single response type used for **all three goals**
(explore/profession/university) — see §6 for why there is one shape rather
than three separate top-level response types.

```json
[
  {
    "id": "...",
    "assessment_id": "5c1e6c0a-...-...",
    "direction_slug": "architect",
    "direction_name": "Архитектура",
    "goal": "profession",
    "profession_options": [
      {
        "title": "Архитектор",
        "why": "Высокий балл по пространственному мышлению",
        "practice": []
      }
    ],
    "subjects_now": [
      { "subject": "Математика", "weight": 3, "note": "Уже сильная сторона — держи темп" }
    ],
    "starter_actions": ["Попробуй бесплатный курс по черчению на Stepik"],
    "growth_focus": {
      "weakness": "Слабая усидчивость на длинных задачах",
      "why_it_matters": "Архитектурные проекты требуют многочасовой концентрации",
      "evidence": "Среднее время на вопрос теста — ниже медианы по треку"
    },
    "skills_to_build": ["Черчение", "3D-моделирование"],
    "university_requirements": [
      {
        "program_name": "Архитектура (бакалавр)",
        "university_name": "КазГАСА",
        "city": "Алматы",
        "exams": ["ЕНТ", "Творческий экзамен"],
        "admission_requirements": [],
        "admission_summary": "",
        "application_deadline": "2026-07-25",
        "grants": [
          { "name": "Госгрант", "amount": "Полная оплата", "conditions": "Конкурсный отбор" }
        ],
        "language_level": "IELTS 6.5",
        "portfolio_needed": true,
        "required_documents": ["Мотивационное эссе"]
      }
    ],
    "stages": [
      { "horizon": "month_1", "title": "Ближайший месяц", "tasks": [] },
      { "horizon": "months_3", "title": "Ближайшие 3 месяца", "tasks": [] },
      { "horizon": "months_6", "title": "Ближайшие 6 месяцев", "tasks": [] },
      { "horizon": "months_12", "title": "12 месяцев", "tasks": [] },
      { "horizon": "until_admission", "title": "До поступления", "tasks": [] }
    ]
  }
]
```

### `ProfessionOption.practice` [TASK #5 groundwork, populated by #10]

Reuses `RoadmapTask` — the same "concrete thing to do, optionally with
resources" shape already used inside `stages[].tasks` — rather than
inventing a second per-profession task shape:

```json
{
  "title": "Архитектор",
  "why": "...",
  "practice": [
    { "text": "Построй макет здания", "category": "practice", "priority": 1, "resources": [] }
  ]
}
```

**As of #10, populated for `goal == "profession"` only** — 1-2 items per
profession, `category` always `"practice"`, `priority` sequential from 1,
`resources` always `[]` (no course/book/club catalog exists yet, same rule
as everywhere else this schema touches resources). Every other goal
(`explore`/`unsure`/`university`/`known`) still gets `practice: []` for
every profession — see §8.

---

## 3. Stage storage [TASK #2 — RESOLVED]

**Decision (project owner): typed JSONB column, same convention as every
other field on `DirectionRoadmap`.**

`direction_roadmaps.stages` (JSONB, `NOT NULL DEFAULT '[]'`) holds
`list[RoadmapMilestone]` serialized the same way `profession_options`,
`subjects_now`, etc. already are — one independently-queryable/updatable
JSONB column per semantic field, not a single all-in-one blob and not
normalized `roadmap_milestones`/`roadmap_tasks` tables.

Rationale (the fact that decided it, per the project owner): **the plan is
always read and regenerated as a whole** — there is no per-task completion
tracking, no "mark this task done" endpoint, no client-addressable task ID.
That rules out normalized rows (only useful once individual tasks need to be
addressed/updated independently) and makes the typed-column approach
strictly better than a single blob (same round-trip cost, but each field
stays independently queryable if a future need arises).

Migration: `alembic/versions/0041_add_stages_to_direction_roadmap.py`.
Existing `direction_roadmaps` rows predating this migration get the column
default `[]`, **not** a backfilled skeleton — they go stale and are
overwritten the next time that direction's plan is regenerated, same as any
other field on this row. No backfill migration was written; this matches
how every other field on this table has always behaved (there's no history
of backfilling `direction_roadmaps` after a shape change — see migration
`0034`, which dropped and replaced 4 columns with no backfill either).

The environment note in an earlier draft of this doc about a stray
same-named `stages` column and an unreachable, more advanced dev-DB
implementation (separate `explore_roadmaps` table, `RoadmapPlatform` enum,
etc.) has been resolved outside of this doc's scope — that drift was
cleaned up, the dev DB was confirmed at `alembic 0040 (head)` before this
migration was written, and this `stages` column is a fresh addition, not a
resurrection of that column or its data. See §7 for what remains
unresolved from that finding (mainly: nobody has recovered whatever logic
built that dev-DB implementation, if it's worth recovering at all).

---

## 4. Language / portfolio / documents [TASK #4 — RESOLVED]

**Decision (project owner): structured fields, same precedent as
`application_deadline`/`grants` (#11).** Backend-populated from
`Program.requirements`, zero LLM involvement — consistent with the "real
facts vs thin LLM layer" split this schema has held everywhere else.

Three new fields on `UniversityRequirement`:

| Field | Type | Source |
|---|---|---|
| `language_level` | `str \| None` | `Program.requirements["min_ielts"]`, formatted `"IELTS {value}"` |
| `portfolio_needed` | `bool \| None` | `Program.requirements["needs_portfolio"]`, verbatim |
| `required_documents` | `list[str] \| None` | Built from `needs_essay`/`needs_recommendations` |

### The null-means-no-data rule (explicitly called out — this is the part
that actually mattered in this decision)

`None`/absent **must mean "no data"**, never "not required" — those are
different facts and the frontend must render them differently (something
like "нет данных" vs "не требуется", not the same blank state for both).
Concretely, per field:

- **`language_level`**: `None` when `Program.requirements` has no
  `min_ielts` key at all (no data), **and also** when the key is present
  but explicitly `null` (some seeded programs — mostly creative-exam
  programs — carry `"min_ielts": None` on purpose, meaning "confirmed: no
  language minimum for this program"). Both collapse to the same `None`
  output on purpose: unlike a bool, a language level has no third value to
  represent "confirmed not required" separately from "unknown" — there's
  either a level to report or there isn't.
- **`portfolio_needed`**: `None` **only** when `needs_portfolio` is absent
  from `Program.requirements` (no data yet on this program). A real
  `False` is passed through as `false`, never collapsed into `None` — this
  is the field where the distinction is most visible, since a bool has
  room for exactly three states (`true`/`false`/`null`) and this schema
  uses all three on purpose.
- **`required_documents`**: `None` when `Program.requirements` has neither
  `needs_essay` nor `needs_recommendations` (no data at all); an empty
  list `[]` when the keys are present but both false (confirmed: no extra
  documents needed) — `[]` and `None` are different facts here too.
  `needs_interview` is deliberately **not** represented in this field — an
  interview is a process step, not a document to hand in; it isn't
  currently exposed anywhere on `UniversityRequirement`.

Implementation: `app/services/roadmap_builder.py`,
`_language_level_for` / `_portfolio_needed_for` / `_required_documents_for`,
wired into `_university_requirements_for`. All three are pure functions of
`Program.requirements` — see `tests/integration/test_roadmap_builder.py`
for the null-vs-not-required test coverage (both directions, for all three
fields).

Fill rate: ~31% of programs have this data at all today (see §5) — so
**most `university_requirements` entries will show these three fields as
`null` today**, not because nothing was implemented, but because the
source data doesn't exist yet for most programs. This is expected, not a
bug — frontend should design the "no data" state as a first-class case,
not an edge case.

---

## 5. `Program.deadlines`/`grants`/`requirements` fill rates in the dev DB [TASK #3]

Queried directly against the dev Postgres, most recently 2026-08-04:

| Field | Populated | Of | % |
|---|---|---|---|
| `deadlines` (non-empty) | 62 | 1483 | 4.2% |
| `grants` (non-empty) | 1483 | 1483 | 100%, but 1478/1483 have exactly **one** generic entry (name usually "Госгрант") |
| `requirements` (non-empty at all) | 1483 | 1483 | 100% (almost always just `exams`/`ent_subjects`) |
| `requirements.min_ielts` / `needs_portfolio` / `needs_interview` / `needs_essay` / `needs_recommendations` / `min_gpa` / `min_sat` | ~458–460 | 1483 | ~31% |
| `requirements.min_ent` | 80 | 1483 | 5.4% |
| `requirements.profile_subjects` | 10 | 1483 | 0.7% |
| `requirements.admission_requirements` / `admission_summary` (read by the current code) | 0 | 1483 | 0% — dead fields, pre-existing |

Implication for university-goal plan richness: deadlines will show on ~4%
of programs today, grants will show on essentially all of them (but as one
generic line, not per-program detail), and the structured
language/portfolio/documents fields from §4 will be non-null on roughly a
third of programs.

---

## 6. Why one shared response shape instead of three goal-specific types [TASK #5]

The three goals (`explore` / `profession` / `university`) diverge in
**content**, not in top-level response shape:

- **university**: the goal-specific richness lives in
  `university_requirements` (§4/§1.3) — deadlines, grants, language,
  portfolio, documents. Fully implemented.
- **profession**: the goal-specific richness is `profession_options`
  growing to 3-5 entries with per-profession `practice` (§2) — schema
  groundwork laid (the `practice` field exists and round-trips), content
  generation is task #10, out of scope here.
- **explore**: "try several things" is expressed structurally by calling
  `POST /directions` with **multiple** `direction_slugs` and getting back
  multiple `DirectionRoadmapResponse` entries — one per direction being
  tried on — rather than by a different response shape. This already
  works today via the #8 (0..N directions) endpoint; nothing new was
  needed for this goal specifically.

This was a **deliberate simplification, not an oversight** — it follows
directly from #2's resolution (§3): storage is one shared `direction_
roadmaps` table with typed JSONB columns, not per-goal tables. A response
type is a thin wrapper over that storage, so a single `DirectionRoadmap
Response` used for all three goals, with goal-dependent *content* inside
shared fields, was the natural fit. Introducing three separate top-level
Pydantic response types (or reviving the abandoned dev-DB `explore_
roadmaps` table pattern mentioned in an earlier draft of this doc) would
mean re-opening #2's decision, which is explicitly out of scope for this
task.

**Update (2026-08-05): `goal` is now echoed back.** `DirectionRoadmapResponse.
goal: str` (one of `explore`/`profession`/`university`/`unsure`/`known`) —
denormalized from `Assessment.goal` onto `DirectionRoadmap` at generation
time (migration `0042_add_goal_to_direction_roadmap.py`, backfilled for
existing rows via a join on `assessment_id`, then set `NOT NULL`). Set/
refreshed on every (re)generation in `roadmap_builder._upsert_direction_
roadmap`. Lets the frontend render the right UI straight from a roadmap
response without a separate `Assessment` fetch. See §2 for where it sits in
the response shape.

---

## 7. Known environment/test notes

- **Migration `0041`** (`stages` column) applies cleanly on top of `0040
  (head)` — confirmed via `docker compose exec api python -m alembic
  upgrade head` and `alembic current` showing `0041 (head)`.
- **Full integration suite**: 229 passed as of this revision. Three
  pre-existing, unrelated failures reproduce consistently regardless of
  this task's changes (confirmed by running with and without this
  session's diff):
  - `tests/integration/test_seed_akinator_content.py::test_seed_creates_expected_rows`
  - `tests/integration/test_seed_akinator_content.py::test_rerun_creates_no_duplicates`
  - `tests/unit/test_seed_akinator_content_data.py::test_counts_match_acceptance_criteria`
    (newly noticed this session — same root cause as the other two: seeded
    `SPECIALTIES` count is 56, tests assert 38. Unrelated to roadmap work;
    nothing in this task touches `scripts/seed_akinator_content.py`.)
- Two more tests were observed failing **intermittently**, only when run as
  part of the full suite, never in isolation, and their failure/pass
  pattern was unrelated to whether this session's diff was applied:
  `test_program_direction_slugs.py::test_devops_program_found_by_*` and
  `test_akinator_router.py::test_sequential_answers_reach_a_valid_reveal`.
  Both pass reliably in isolation (`pytest <file>::<test>` alone, repeated).
  This looks like pre-existing test-isolation state bleed somewhere in the
  suite (unrelated to `direction_roadmaps`/`roadmap_builder`, which this
  task touched) — flagged for whoever owns test infra next, not something
  this session chased down further since it doesn't reproduce against this
  task's own changed code paths.
- Whoever recovers or investigates the abandoned dev-DB `explore_roadmaps`/
  advanced `stages` implementation mentioned in earlier drafts of this doc
  (§3) should know: that data no longer exists in a form this doc's `0041`
  migration interacts with. The dev DB was already reset to `0040 (head)`
  before this session started, so this migration was written and applied
  against clean ground, not against that abandoned schema.

---

## 8. Tasks #1/#9/#10 — explore auto-selection & profession expansion [shipped 2026-08-04]

Landed on top of the schema described above with **no response-shape
changes** — same `DirectionRoadmapResponse`, same `ProfessionOption`/
`RoadmapTask` types. Only content generation changed.

### 8.1 Task #1 — direction source for explore [decided by the prior
session, executed here]: `AssessmentSession.belief`, same signal
`StudentContext.leaning_directions` is built from.

### 8.2 Task #9 — explore/unsure: empty `direction_slugs` auto-resolves

`POST /directions` with `direction_slugs: []` and `goal in (explore,
unsure)`: resolves to the top 3 leaf slugs by `belief`
(`roadmap_builder._EXPLORE_AUTO_DIRECTION_COUNT`), filtered to slugs that
still resolve to a real `Direction` row (stale belief entries are silently
skipped, not 404'd), then generates one `DirectionRoadmapResponse` per
resolved slug through the existing unmodified per-direction pipeline. The
list-of-responses shape (§1.1) is what does the "grouping by direction" work
for explore's "try several things" framing — **no new field was added for
this**, see 8.4 for why.

For any other goal, or an explore/unsure assessment with no belief signal
yet, empty `direction_slugs` still 400s (`roadmap_builder.
_EMPTY_SLUGS_WRONG_GOAL` / `_EMPTY_SLUGS_NO_SIGNAL`).

`_EXPLORE_AUTO_DIRECTION_COUNT = 3` is an **implementation-level choice, not
a schema decision** — chosen to match the profession expansion's upper
bound (8.3) and to keep an auto-triggered batch to a bounded number of LLM
calls. Flagged here in case product wants a different N; changing it needs
no schema change, just the constant.

The prompt's `starter_actions` guidance (`app/prompts/direction_roadmap.py`,
"ЦЕЛЬ «ПОНЯТЬ СЕБЯ»" section) now nudges the model toward the client's
literal activity vocabulary for `goal in (explore, unsure)` — trial
course/lesson, joining an existing club, a small project, finding a way to
talk to someone in the field, olympiad problems, lectures — while keeping
every existing hard constraint (allowed-platforms whitelist, one-student-
doable, no invented course/org names, age-appropriate depth) unchanged. The
structural bounds on `starter_actions` (2-3 items) were **not** changed to
match the client's literal "1-2" wording — 2 already satisfies both ranges,
and re-opening a tested structural invariant for a one-item difference
wasn't judged worth it. Flagged in case product disagrees.

### 8.3 Task #10 — profession goal: 3-5 professions + practice

`profession_options` count now depends on goal
(`direction_roadmap.profession_option_bounds`, shared by the prompt and the
`_valid_plan` structural guard so they can never drift apart):

| Goal | Range | Notes |
|---|---|---|
| `profession` | 3-5 | Capped by how many professions the direction's own catalog (`Direction.professions`) actually has — a direction with only 2 professions total returns 2, honestly, same principle as the `why` rule below |
| every other goal | 1-3 | Unchanged from before this task |

The `why`-honesty rule (§ "why is deliberate anti-hallucination guardrail")
is **unchanged and unrelaxed**: `why` is still null per-profession unless a
real distinguishing signal exists for that specific profession. Widening
the count to 3-5 for `profession` does not mean 3-5 professions all get a
`why` — most will legitimately be `null`, and that is the correct, honest
output, not a shortfall.

`practice` (1-2 `RoadmapTask` items per profession, `goal == "profession"`
only): the LLM supplies only `text` per item; `category` (`"practice"`),
`priority` (sequential from 1) and `resources` (always `[]`) are backend-
assigned (`roadmap_builder._practice_for` / `_profession_options_for`) —
same real-facts-vs-thin-LLM-layer split as every other field in this
module. Each item is grounded in one of two genres per the prompt: "try the
profession in practice" (mini-project, practice-style task, existing
competition/olympiad) or "which course to take / existing club to join"
(same allowed-platforms whitelist and no-invented-name rules as
`starter_actions`).

### 8.4 Interpretation decisions made (not schema changes) — flagged for the
project owner to override if this reading is wrong

- **"Какие кружки или курсы подходят" (client's spec) is not a distinct
  field.** A course/club recommendation is structurally identical to what
  `starter_actions` and `practice` already produce under the existing
  platform-whitelist rules (e.g. "пройди вводный курс на Stepik" *is* a
  course recommendation; "вступи в кружок робототехники" *is* a club
  recommendation). Folded into `practice`'s second genre (8.3) instead of
  adding a 4th near-duplicate field.
- **"Какие навыки нужны" / "какие предметы важны" stay plan-level**
  (`skills_to_build`/`subjects_now`), **not** duplicated per-profession on
  `ProfessionOption`. Reasoning: making these per-profession would require
  the LLM to differentiate skill/subject claims across up to 5 professions
  per response, which is exactly the kind of finer-grained claim the
  `why=null`-unless-distinguishing guardrail exists to prevent elsewhere in
  this same prompt — the existing plan-level fields, read together with
  `profession_options`, already answer "what do I need for this direction
  in general" without that added hallucination surface. **This is the one
  item in this section closest to a real product-scope question rather
  than a pure implementation call** — if the project owner wants true
  per-profession skill/subject breakdowns later, that's a new field and a
  new prompt section, not a reinterpretation of existing ones.
- **`stages[].tasks` is still not filled by #9/#10.** Confirmed against
  `docs/roadmap-content-generation.md`'s own finding: laying generated
  content out across the 5 horizons (1/3/6/12 months + until_admission) is
  a distinct, still-unassigned piece of work, not something #9/#10's
  per-direction/per-profession content generation implies. `stages` remains
  the empty skeleton from task #6/#12.

### 8.5 Tests / verification

`tests/integration/test_roadmap_builder.py` — new coverage for
`profession_option_bounds`, `build_retry_hint`, `_valid_plan`'s
goal-dependent profession-count/practice checks, `_practice_for`/
`_profession_options_for`, `_resolve_explore_direction_slugs` (signal-empty
400, wrong-goal 400, stale-slug filtering, top-N-by-belief ordering), and an
`_upsert_direction_roadmap` round-trip for a profession-goal plan with
practice. Full suite: see this doc's own §7 for the pre-existing baseline:
after this task's changes, `docker compose exec api python -m pytest -q`
reports 250-252 passed / 255 total across two runs, with failures limited to
exactly the already-documented set (3 pre-existing `seed_akinator_content`
failures + the 2 known-flaky tests, which reproduced on one of the two runs
and not the other, consistent with their documented "intermittent, full-suite-only"
behavior) — no new failures introduced.
