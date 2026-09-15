# Scope estimate: collapse bank-seeded content from row-per-locale to one row + JSONB text

## Context

`docs/i18n-contract.md` §8 documents "variant A" locale storage for the five
bank-seeded content tables (`questions`, `question_pairs`,
`motivation_statements`, `motivation_pairs`, `directions`): one logical
content unit = one physical row **per locale**, sharing a natural key
(`order`, `pair_index`, `(triplet_index, order)`, `slug`) but each row
carrying its **own independent copy** of every column — including
"structural" fields the contract says must stay identical between locale
twins (`riasec_type`, `bigfive_domain`, `mi_category`, `facet`, `keyed`,
`age_tier`, `holland_code`, ...).

Nothing in the code enforces that invariant. `AdminQuestionUpdateRequest`
(`app/schemas/admin_content.py:56-65`) lets an admin PATCH a single
locale-row's `riasec_type` via `PATCH /admin/questions/{id}`, and
`_validate_question_update` (`app/services/admin_content_service.py:71-77`)
only rejects a `null` type field — it does not check the row's locale twin at
all. Concretely: if an admin edits the `kk` copy of question `order=5` and
changes `riasec_type` from `R` to `S`, the `ru` copy stays `R`, and from then
on a student who takes the test in Kazakh has that answer scored as `S` while
a Russian-speaking student answering "the same" question scores it as `R` —
silent data corruption, not a crash, and nothing in the current test suite
would catch it (ru and kk are tested independently, each internally
consistent).

The proposed fix ("variant B") collapses each logical unit back to **one**
physical row: structural fields become ordinary single-value columns (no
locale-twin to desync from — the field only exists once), and only display
text (`text`, `short_text`, `frame`, `option_a_text`/`option_b_text`,
`description`, ...) becomes a locale-keyed JSONB column (`{"ru": ..., "kk":
...}`), read via a `resolve_column_i18n`/`pick_locale`-style helper. This is
not new engineering territory — it's the same pattern already live in
production for `University.description_i18n` / `Program.name_i18n`
(`app/i18n/__init__.py:206-229`, consumed by `app/services/university_service.py`).

This document scopes what a full migration to variant B would touch, so the
team can decide whether to do it now, do a cheaper stopgap, or defer. It does
not implement anything.

## Cheaper alternative, for comparison

Before committing to the full refactor: a guard-rail patch to
`_validate_question_update` (and its equivalents for the other 4 tables)
that looks up the locale-twin row by natural key and rejects a structural
edit that would create a mismatch (or mirrors the edit to both rows) closes
the specific bug in a few hours, without touching the schema, seed scripts,
or any read path. It doesn't remove the duplicated-row model or the
`content_locale.py` fallback machinery, and it doesn't fix the adjacent
`directions` ambiguity noted below — but it's the right size if the team
isn't ready to absorb the full refactor below.

## Shared infrastructure affected regardless of table

- `app/models/content_locale_column.py` — the `locale_column()` factory all
  5 models use. Removed or repurposed.
- `app/services/content_locale.py` — `localized_rows()`, the variant-A
  per-natural-key display-read helper with `ru` fallback. Used by 6 service
  files (below). Replaced by `resolve_column_i18n`/`pick_locale`
  (`app/i18n/__init__.py`), already proven for University/Program.
- `app/services/admin_lock.py` — `apply_overrides`/`sync_fields`, generic
  over a row's `overrides` JSONB. This is the exact mechanism that lets two
  locale-twin rows desync today (line 26-34: mutates one row fetched by
  UUID, no notion of a sibling row). Needs to stay for the override
  mechanism itself, but the desync risk it currently carries disappears once
  there's only one row per logical unit.
- `alembic` — `d80fbf5d1f43` (owns the `locale_enum` Postgres type, via
  `users.locale`) must survive untouched; `f3b9c1d47a20` (adds the `locale`
  column to all 5 tables) is superseded by the new collapse migration(s).

## Scope by table, riskiest to safest

### 1. `questions` — riskiest

Real per-student history references specific locale-row UUIDs:
`user_responses.question_id` (`UUID NOT NULL`, `ON DELETE CASCADE`) and
`question_pairs.question_a_id`/`question_b_id` both point at one specific
locale copy of a `Question` row, not at a locale-independent identity.
Collapsing to one row per `order` requires, per row being dropped:

1. Pick the surviving UUID (the `ru` row's, per `ru`-is-canonical convention
   already used for scoring denominators).
2. `UPDATE user_responses SET question_id = <survivor> WHERE question_id =
   <kk-twin>` before deleting the `kk` row.
3. Same remap for `question_pairs.question_a_id`/`question_b_id`.
4. Handle the `uq_user_response_assessment_question` unique constraint
   (`assessment_id, question_id`): if one assessment ever recorded answers
   against **both** locale copies of the same logical question — plausible
   on a retake across a locale switch, since `assessment_shared.invalidate_retake`
   reuses `assessment_id` — the remap collides on that constraint and needs
   an explicit tiebreak (e.g. keep the later `created_at`, drop the other).

Touches 3 seed scripts (RIASEC/Big Five/MI questions share this one table),
4 scoring services (`riasec_service`, `bigfive_service`, `mi_service`,
`assessment_shared`), `question_service.get_all_questions`,
`question_pair_service._to_option`, `admin_service`'s admin transcript view
(reads `.text` with **no** locale resolution at all today —
`app/services/admin_service.py:404`), and `admin_content_service`'s
list/detail/update trio.

`tests/integration/test_content_locale.py::test_structural_fields_match_between_ru_and_other_locales`
(line 265) is written *against* today's bug risk — it becomes meaningless
(there's only one row to compare) and should be deleted, not fixed.

### 2. `motivation_statements` — second riskiest

Same category of real per-student FK: `MotivationResponse.most_statement_id`
/ `.least_statement_id` (`UUID NOT NULL`, `CASCADE`). Lower collision risk
than `questions` — the response table's own unique constraint is
`(assessment_id, triplet_index)`, not `(..., statement_id)`, so the remap
can't hit a duplicate-key case the way `questions` can. Touches 1 seed
script, `motivation_service` (triplets/scoring/submit), and the admin
content trio. `app/routers/motivation.py` layers an *age-tier* override
(`text_junior` for junior vs `text` otherwise) on top of whatever locale
resolution returns — that composition must keep working once both fields
are JSONB.

### 3. `question_pairs` — moderate

No inbound FK of its own, but its two outbound FKs
(`question_a_id`/`question_b_id`) must be repointed in lockstep with the
`questions` collapse — **this table cannot be migrated independently of
`questions`**; an intermediate state where `questions` has collapsed but
`question_pairs` hasn't would leave pairs pointing at now-deleted `kk`
`Question` rows. Treat `questions` + `question_pairs` as one migration unit.
`question_pair_service.get_pairs`/`submit_pair_answers` currently
re-resolves the pair per-locale specifically to keep the shown pair and the
validated pick on matching UUIDs (`app/services/question_pair_service.py`
comment, lines ~112-117) — that whole workaround goes away once there's one
canonical `Question` row regardless of locale.

### 4. `motivation_pairs` — low

`MotivationPairResponse` scores by `pair_index` (a plain int) in Python —
confirmed **no FK column** on `MotivationPairResponse` points at
`motivation_pairs.id` at all. Collapsing the two locale rows to one is a
pure de-dup with zero downstream ID remapping, anchored on the real DB
unique constraint `uq_motivation_pairs_pair_index_locale` that already
exists. Cheapest table to migrate, and a reasonable first candidate to prove
the pattern (schema change, seed rewrite, admin schema shape, read-path
swap) before spending it on a table with real FK-remap risk.

### 5. `directions` — safest structurally, widest fan-out

No per-user ID-based FK — `Assessment.selected_direction_slug` stores a
**slug string**, not a `direction_id`. The only inbound FK
(`program_directions` M2M, `ON DELETE CASCADE`) is catalog data populated by
idempotent, rerunnable scripts (`build_universities.py`,
`seed_kz_universities.py`, `seed_92_professions_universities.py`) — worst
case it can be regenerated rather than surgically remapped.

The cost here is breadth: **11 service files** read `Direction`
(`direction_service`, `riasec_service`, `goal_overlay_service`,
`report_service`, `roadmap_builder`, `university_service`, `riasec_content`,
`direction_inquiry_service`, plus the admin trio and router). Two adjacent
findings worth fixing in the same pass, not new bugs the refactor
introduces:

- `goal_overlay_service.py` has 4 sites (lines 317-319, 349, 451-453, 464)
  that explicitly pin `Direction.locale == DEFAULT_LOCALE` with a comment
  acknowledging the gap — these simplify to a plain unfiltered read once
  there's one row, and can additionally start localizing `direction.name`
  for free.
- `build_universities.py` / `seed_kz_universities.py` /
  `seed_92_professions_universities.py` build `directions_by_slug = {d.slug:
  d for d in ...}` **unfiltered by locale** — with two rows sharing a slug,
  whichever row the DB happens to return last silently wins the dict key,
  and that's the row `program_directions` actually links to today. Not a
  crash (`roadmap_builder.py:751` and `university_service.py:89` both join
  rather than `.scalar_one()`, so no `MultipleResultsFound`), but an
  accidental-correctness situation that the collapse resolves by
  construction rather than by audit.

Also seeds an extra, easy-to-miss script:
`scripts/apply_direction_content.py`, which fills
`description`/`skills_needed`/`subjects_to_develop`/`first_steps` from
reviewed JSON files *separately* from `seed_riasec_directions.py` (which
only handles `name`/`slug`/`holland_code`) — both need rewriting.

## Total footprint

| Category | Count | Notes |
|---|---|---|
| Models | 6 | 5 content models + `content_locale_column.py` (removed/repurposed) |
| Seed/apply scripts | 8 | all `seed_*.py` for the 5 tables, plus `apply_direction_content.py` |
| Services | 15 | `content_locale.py` (removed), `admin_lock.py`, `admin_content_service.py`, `admin_service.py`, `question_service.py`, `question_pair_service.py`, `motivation_service.py`, `motivation_pair_service.py`, `direction_service.py`, `riasec_service.py`, `bigfive_service.py`, `mi_service.py`, `assessment_shared.py`, `goal_overlay_service.py`, `university_service.py` |
| Routers | 1 | `admin.py` (locale params + response shape on 5 endpoint groups) |
| Schemas | 6 | `admin_content.py` (major rewrite), 5 model-adjacent Pydantic schemas (minor/verify) |
| Tests | 13 | see per-table sections; `test_content_locale.py` and `test_admin_content_locale.py` need the largest rewrites |
| Migrations | 2 existing referenced + N new | `f3b9c1d47a20` superseded, `d80fbf5d1f43` untouched; one new collapse-and-remap migration per table (not yet written) |

**≈ 51 existing files touched**, plus new Alembic migrations, across the 5
tables' shared infrastructure. This is a multi-PR backend refactor, not a
single-sitting change — see sequencing below.

## Open product/design decisions (block starting until answered)

1. **Admin edit shape for bilingual text.** One PATCH with `text: {"ru":
   ..., "kk": ...}` (edit both at once), or two discrete fields (`text_ru`,
   `text_kk`) editable independently? Affects `admin_content.py` schemas and
   the admin frontend contract (`docs/frontend-admin-questions-api-contract.md`
   would need a matching update).
2. **Is `icon` actually locale-independent?** `Question.icon`,
   `QuestionPair.option_a_icon`/`option_b_icon` are emoji — almost certainly
   shared, not translated, and should become plain structural columns rather
   than JSONB. Worth confirming there's no existing kk-specific icon
   override in the bank files before assuming this.
3. **Retake-collision tiebreak for `questions`.** Confirm the "keep latest
   `created_at`" rule (or another) for the rare case where one assessment
   answered both locale copies of the same question before the migration
   runs.

## Suggested sequencing

Given the dependency (`question_pairs` can't move independently of
`questions`) and the risk gradient above:

1. **`motivation_pairs`** first — lowest risk, no FK remap, proves the full
   pattern (model, seed rewrite, admin schema, read-path swap) end to end
   before it's applied anywhere with real remap risk.
2. **`directions`** — still no per-user FK risk; forces auditing the 11
   read-sites and fixing the `goal_overlay_service`/`program_directions`
   tech debt noted above as a side effect.
3. **`motivation_statements`** — first table with real FK remap, but
   mechanical (no collision case).
4. **`questions` + `question_pairs` together**, last — highest risk
   (collision-prone remap, widest instrument fan-out), done once the remap
   tooling/approach is already proven on step 3.

Each step is its own migration + PR; do not batch multiple tables into one
migration given the remap risk on steps 3-4.
