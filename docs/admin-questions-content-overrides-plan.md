# Admin editing for questions/pairs/motivation content, protected from seed resync

## Context

Same underlying problem as the already-approved university/program plan
(`docs/admin-edit-lock-plan.md`) — admin editing needs to survive the seed
scripts that run on every CD deploy — but applied to the question-bank
content (RIASEC/Big Five/MI questions, forced-choice pairs, motivation
statements/pairs, RIASEC directions), which today has **zero admin editing
at all** and is **riskier** than the university case.

Read all 7 relevant seed scripts in full
(`seed_riasec_questions.py`, `seed_bigfive_questions.py`,
`seed_mi_questions.py`, `seed_question_pairs.py`,
`seed_motivation_statements.py`, `seed_motivation_pairs.py`,
`seed_riasec_directions.py`) plus the models they write to
(`app/models/question.py`, `question_pair.py`, `motivation.py`,
`motivation_pair.py`, `direction.py`). Every one of them is a **full
resync**, not a partial upsert: for each row in a static Python "bank" file
(e.g. `scripts/riasec_question_bank.py`), it diffs and overwrites specific
fields on the matching DB row (matched by a key — `order`, `pair_index`,
`(triplet_index, order)`, or `slug`), inserts missing rows, and **deletes any
DB row whose key is no longer in the bank**. That last part is new risk the
university plan didn't have to deal with — University/Program rows are never
deleted by a reseed, only individual fields get reverted.

One exception: `seed_riasec_directions.py` only ever diffs `name` and
`holland_code` — the descriptive fields (`description`, `professions`,
`skills_needed`, `subjects_to_develop`, `first_steps`) are never touched
once a `Direction` row exists, so those specific fields need no protection
at all. Only `name`/`holland_code` (and the row's existence, via the
delete-orphans step) are at risk.

## Design (confirmed with user)

User chose the "cleaner but more work" option over reusing
`admin_locked_fields` as-is: **the bank files stay the single source of
content truth; admin edits are recorded as an explicit overrides layer that
the seed scripts compose on top of the bank at sync time** — not a bare
lock flag. Concretely:

- New `overrides: dict` (JSONB) column on `Question`, `QuestionPair`,
  `MotivationStatement`, `MotivationPair`, `Direction` — e.g.
  `{"text": "Admin-edited wording", "icon": "🎯"}`. Unlike a plain
  `field_name` list, this **stores the actual overridden value alongside
  the lock**, so the override is self-documenting/recoverable from the row
  itself, not just "don't touch this" with the value living only in the
  live column.
- Admin PATCH writes to both the live column (immediate effect, same as
  today's `University`/`Program` PATCH) and into `overrides` in the same
  call — the live column is still what every other part of the app reads
  (scoring, assessment rendering, etc. all query `Question`/`QuestionPair`/
  etc. directly in many places; making every reader merge bank+overrides
  itself would be a much larger, riskier change than the seed scripts
  already being the one place that reconciles bank vs. DB).
- Seed scripts change their diff step from *"does the bank value differ
  from the DB value? if so, overwrite"* to *"is this field admin-overridden?
  if so, keep the DB value; otherwise sync from the bank as before."*
- Seed scripts' delete-orphans step additionally skips any row that has
  **any** override at all (even if the specific overridden field isn't
  what would've triggered the delete) — an admin-edited question shouldn't
  vanish just because its `order` moved in the bank file.
- Same choices as the university plan, carried over for consistency: **no
  unlock endpoint for now**, **PATCH-only** (no admin create/delete of
  questions — out of scope), and this reuses/extends the same shared helper
  module (`app/services/admin_lock.py`) planned for the university work
  rather than inventing a parallel one, since both are "protect an admin
  edit from an automated resync" — the two mechanisms differ in shape
  (`admin_locked_fields: list[str]` for University/Program,
  `overrides: dict` for question content) because the failure modes differ
  (field-revert only vs. field-revert *and* row-deletion), not because they
  need different philosophies.
- **Known limitation, inherent to key-based matching (not solved here)**:
  these seed scripts match DB rows to bank entries by a key (`order`,
  `pair_index`, etc.), not by identity. If someone reorders the bank file
  such that a *different* bank entry now lands on the same key as a row
  with an override on an unrelated field, that row's non-overridden fields
  will sync to the new bank entry's content while the overridden field(s)
  stay put — a pre-existing quirk of key-based sync, not something either
  design (lock-list or overrides-dict) fixes.

## Changes

### 1. Extend `app/services/admin_lock.py` (shared with the university plan)
Add, alongside the existing `lock_fields`/`is_locked`:
```python
def apply_overrides(row, updates: dict) -> None:
    overrides = dict(row.overrides or {})
    for key, value in updates.items():
        setattr(row, key, value)
        overrides[key] = value
    row.overrides = overrides

def effective_value(row, field_name: str, bank_value):
    overrides = row.overrides or {}
    return overrides[field_name] if field_name in overrides else bank_value

def has_overrides(row) -> bool:
    return bool(row.overrides)
```

### 2. Models + migration
Add `overrides: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)`
to:
- `app/models/question.py::Question`
- `app/models/question_pair.py::QuestionPair`
- `app/models/motivation.py::MotivationStatement`
- `app/models/motivation_pair.py::MotivationPair`
- `app/models/direction.py::Direction`

One new Alembic migration adding this column (default `'{}'::jsonb`) to all
five tables — bundle with (or stack directly on top of) the
`admin_locked_fields` migration from the university plan since both are
small additive JSONB columns; resolve the real head via `alembic heads` at
implementation time.

### 3. New admin service — `app/services/admin_content_service.py`
Same shape as `admin_university_service.py`'s `list_universities`/
`get_university_detail`/`update_university`, repeated per entity:
- `list_questions(db, *, instrument, age_tier, search, page, limit)`,
  `get_question_detail`, `update_question` (uses `apply_overrides`, mirrors
  `update_university`'s fetch-or-404 → apply → commit → refresh shape).
- `list_question_pairs`, `update_question_pair`.
- `list_motivation_statements`, `update_motivation_statement`.
- `list_motivation_pairs`, `update_motivation_pair`.
- `list_directions`, `update_direction` — same mechanism even though only
  `name`/`holland_code` are ever at risk, for one consistent code path
  rather than a special-cased exception.

### 4. New schemas — `app/schemas/admin_content.py`
Same List/Detail/UpdateRequest pattern as `app/schemas/admin_university.py`,
one triplet per entity. `*Detail` schemas include `overrides: dict` (per
user decision — same visibility choice as `admin_locked_fields` in the
university plan) so the admin UI can show which fields are admin-owned.
`*UpdateRequest` schemas expose exactly the fields each seed script diffs
(the "at risk" fields listed in the Context table above) — no need to
expose fields the seed scripts never touch (e.g. `Question.instrument`,
`QuestionPair.question_a_id`/`question_b_id` stay read-only; changing which
question a pair points to is a structural edit, not a content edit, and out
of scope here).

### 5. New admin routes in `app/routers/admin.py`
`GET`/`PATCH` pairs, gated by the existing `Depends(get_current_admin_user)`,
mirroring the university routes exactly:
- `/admin/questions`, `/admin/questions/{id}`
- `/admin/question-pairs`, `/admin/question-pairs/{id}`
- `/admin/motivation-statements`, `/admin/motivation-statements/{id}`
- `/admin/motivation-pairs`, `/admin/motivation-pairs/{id}`
- `/admin/directions`, `/admin/directions/{id}`

### 6. Patch all 7 seed scripts to compose bank + overrides
For every per-field diff (e.g. `seed_riasec_questions.py:52-66`,
`if existing.riasec_type != riasec_type: existing.riasec_type = riasec_type`),
change to:
```python
target = effective_value(existing, "riasec_type", riasec_type)
if existing.riasec_type != target:
    existing.riasec_type = target
```
for each diffed field, and in the delete-orphans loop
(`seed_riasec_questions.py:79-82`), skip + log rows with `has_overrides(row)`:
- `seed_riasec_questions.py` — fields `riasec_type`, `text`, `age_tier`,
  `short_text`, `icon`.
- `seed_bigfive_questions.py` — `bigfive_domain`, `facet`, `keyed`, `text`,
  `age_tier`, `short_text`, `icon`.
- `seed_mi_questions.py` — `mi_category`, `text`, `age_tier`, `short_text`,
  `icon`.
- `seed_question_pairs.py` — `age_tier`, `frame`, `option_a_text`,
  `option_b_text`, `option_a_icon`, `option_b_icon`.
- `seed_motivation_statements.py` — `category`, `text`, `text_junior`.
- `seed_motivation_pairs.py` — `category_a`, `category_b`, `text_a`,
  `text_b`.
- `seed_riasec_directions.py` — `name`, `holland_code` only (its other
  fields already need no protection, per Context).

## Not in scope (consistent with the university plan's decisions)
- No unlock endpoint.
- No admin create/delete of questions/pairs/statements/directions — PATCH
  of existing rows only.
- No change to how the rest of the app reads these tables — scoring,
  assessment rendering, roadmap generation etc. keep reading the live
  columns directly, unaffected by this change.

## Verification

1. Run the new migration locally, confirm `overrides` defaults to `{}` on
   all five tables.
2. `PATCH /admin/questions/{id}` with `{"text": "New wording"}` — confirm
   the response's `overrides` includes `{"text": "New wording"}`.
3. Run `python scripts/seed_riasec_questions.py` locally — confirm that
   question's `text` survives and a log line notes the field was skipped
   (admin-overridden).
4. Reorder/remove that question's entry from `scripts/riasec_question_bank.py`
   locally, re-run the seed script, confirm the row is **not** deleted
   (logged as skipped due to override) even though its `order` key is gone
   from the bank.
5. Confirm an un-overridden question/pair/statement is still fully
   resynced by its seed script as before (regression check).
6. Confirm `Direction.description`/`professions`/etc. remain editable
   through the new PATCH without needing an override entry (since the seed
   script never touches them) — response reflects the new value
   immediately and stays after a reseed.
