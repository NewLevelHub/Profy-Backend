# Protect admin-edited university/program data from redeploy overwrites

## Context

Admin already has PATCH endpoints for editing universities and programs
(`PATCH /admin/universities/{id}` and the Program equivalent, in
`app/services/admin_university_service.py`) — the ask here isn't "add admin
editing," it's: **make sure a redeploy's seed/backfill scripts don't silently
revert those edits.**

This was a real, confirmed risk, not a hypothetical — every push to `main`/
`dev` runs ~25 scripts sequentially against the live DB (see the long
`docker compose exec api python scripts/X.py` chain in `.github/workflows/
cd.yml` and `cd-dev.yml`). Read all of them (the seed scripts in full, the
apply/backfill scripts touching admin-editable fields in full) to find out
exactly which ones would clobber a manual edit:

| Script | Verdict |
|---|---|
| `seed_92_professions_universities.py` | **Safe** — insert-only, docstring confirms "an existing row is left untouched." |
| `seed_kz_universities.py` (University side) | **Safe in practice** — only fills currently-empty fields (`slug`, `ovpo_code`, `description`, `short_name`, `aliases`, `location`); never overwrites a non-empty value. |
| `seed_kz_universities.py` (Program side) | **Unsafe** — true unconditional upsert: `language`, `cost_per_year`, `description`, `who_its_for`, `career_options`, `deadlines`, `grants`, `directions`, and `requirements.notes` are all written via `setattr` whenever they differ from the static source, no NULL-check. |
| `apply_university_enrichment_2027.py` | **Unsafe** — overwrites `website`, `city`, `location`, `short_name`, `ror_id` whenever current ≠ hardcoded target value (not "if empty"). |
| `backfill_ranking_from_label.py` | **Unsafe** — recomputes `ranking` from `ranking_label` and overwrites whenever it differs from current. |
| `apply_uniranks_kz_2027.py` | **Unsafe** — same overwrite-if-different pattern for `uniranks_kz_rank`/`uniranks_world_rank`. |
| `apply_uniranks_not_ranked.py` | **Unsafe** — forces `uniranks_note = "Н/Р"` whenever current ≠ that. |
| `apply_program_requirements_content_2027.py` | **Unsafe, worst case** — unconditionally overwrites `Program.requirements` keys (`exams`, `needs_portfolio`, `needs_essay`, `needs_recommendations`, `needs_interview`) and `deadlines.application_close` every single run, no comparison at all. |
| `apply_university_descriptions_batch1.py`, `backfill_cost_range.py`, `merge_duplicate_programs.py` | **Safe** — genuinely idempotent (skip-if-already-touched by construction). |

So the answer to "оно при редеплой вообще поменяется?" is **yes, concretely,
for a specific list of fields** — not paranoia, a real gap.

One partial precedent already exists: `scripts/backfill_program_source_
metadata_2026.py` skips a program "if `program.updated_at is not None`"
with the comment *"Skip if already updated/verified by an admin"* — but
that's a one-off, scoped to a single script/field, using a blunt whole-row
signal (any touch sets `updated_at`, not just an admin edit to *that*
field). The fix below generalizes this into a proper mechanism instead of
patching each script differently.

## Design (confirmed with user)

- **New field-level lock, not a row-level flag.** Add `admin_locked_fields:
  list[str]` (JSONB) to `University` and `Program` — the set of top-level
  column names an admin has explicitly PATCHed at least once. Mirrors the
  per-field-path shape already used by this codebase's `fact_sources`
  column (`University`/`Program`) for a different purpose (source
  provenance) — same "list/dict keyed by field name" convention, kept as a
  separate column since the two meanings shouldn't be conflated.
- **Auto-populated, not admin-set.** `update_university`/`update_program`
  already loop over `data.model_dump(exclude_unset=True)` generically
  (`app/services/admin_university_service.py:80-82` and `:104-106`) — after
  that loop, merge `updates.keys()` into `admin_locked_fields`. No schema
  change needed to `AdminUniversityUpdateRequest`/`AdminProgramUpdateRequest`
  — an admin can't set this directly, it's a side effect of any PATCH.
- **No unlock endpoint for now** (per user decision) — once a field is
  admin-locked, only a direct DB/script action can clear it. Cheap to add
  later if needed.
- **Visibility**: expose `admin_locked_fields` on `AdminUniversityDetail`
  and `AdminProgramDetail` (per user decision) so the admin UI can show
  which fields are already protected.
- **Known limitation, not fixed by this plan**: protection only starts once
  this ships. Universities/programs already manually edited *before* this
  change won't be retroactively locked (there's no history of which exact
  fields were hand-edited pre-feature) — an admin would need to re-save
  (re-PATCH, even with the same value) an already-edited row once this is
  live to get it locked going forward.

## Changes

### 1. Shared helper — new `app/services/admin_lock.py`
```python
def lock_fields(row, field_names) -> None:
    locked = set(row.admin_locked_fields or [])
    locked.update(field_names)
    row.admin_locked_fields = sorted(locked)

def is_locked(row, field_name: str) -> bool:
    return field_name in (row.admin_locked_fields or [])
```
Importable both from `app/services/admin_university_service.py` and from
`scripts/*.py` (scripts already import directly from `app.*`, e.g.
`from app.models.university import University` — no shared scripts-utils
module exists yet, so this lives under `app/services/`, not `scripts/`).

### 2. Models + migration
- `app/models/university.py`: add
  `admin_locked_fields: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)`
  (same pattern as the existing `aliases` column).
- `app/models/program.py`: same column.
- New Alembic migration: `ALTER TABLE universities ADD COLUMN
  admin_locked_fields JSONB NOT NULL DEFAULT '[]'::jsonb;` and the same for
  `programs`. Resolve the actual current head via `alembic heads` at
  implementation time (multiple migration branches exist in this repo).

### 3. `app/services/admin_university_service.py`
- `update_university`: after the existing `setattr` loop (line ~82), call
  `lock_fields(university, updates.keys())` before `db.commit()`.
- `update_program`: same, `lock_fields(program, updates.keys())`.

### 4. Schemas
- `app/schemas/admin_university.py`:
  - `AdminUniversityDetail` — add `admin_locked_fields: list[str]`.
  - `AdminProgramDetail` — add `admin_locked_fields: list[str]`.
  (Not added to the `*UpdateRequest` schemas — server-managed only.)

### 5. Patch the six unsafe scripts to respect locks
For each, wrap the write with `if not is_locked(row, "<field>"):` (skip +
log a line like `f"Skipping {field} for {row.id} — admin-locked"` so it's
visible in CD deploy logs):
- `scripts/seed_kz_universities.py` — guard each of `language`,
  `cost_per_year`, `description`, `who_its_for`, `career_options`,
  `deadlines`, `grants`, `directions` in the Program upsert path, and guard
  the `requirements.notes` merge behind `is_locked(program, "requirements")`.
  Also guard the University-side fill-if-empty writes (`slug`, `ovpo_code`,
  `description`, `short_name`, `aliases`, `location`) the same way — belt
  and suspenders for the edge case where an admin intentionally clears a
  field back to empty and a reseed would otherwise "fill" it again.
- `scripts/apply_university_enrichment_2027.py` — guard `website`, `city`,
  `location`, `short_name`, `ror_id`.
- `scripts/backfill_ranking_from_label.py` — guard `ranking`.
- `scripts/apply_uniranks_kz_2027.py` — guard `uniranks_kz_rank`,
  `uniranks_world_rank`.
- `scripts/apply_uniranks_not_ranked.py` — guard `uniranks_note`.
- `scripts/apply_program_requirements_content_2027.py` — guard the whole
  `requirements` update behind `is_locked(program, "requirements")` and the
  `deadlines.application_close` write behind
  `is_locked(program, "deadlines")`.

No changes needed to `seed_92_professions_universities.py`,
`apply_university_descriptions_batch1.py`, `backfill_cost_range.py`, or
`merge_duplicate_programs.py` — already safe by construction.

### 6. Not in scope (per user decision)
- No unlock endpoint/mechanism.
- No retroactive backfill of `admin_locked_fields` for pre-existing manual
  edits (see limitation above).
- Not touching `backfill_program_source_metadata_2026.py`'s existing
  `updated_at is not None` guard — it already does its job for that one
  field; leaving it as-is rather than migrating it to the new mechanism for
  consistency's sake.

## Verification

1. Run the new migration locally (`alembic upgrade head`), confirm both
   `universities.admin_locked_fields` and `programs.admin_locked_fields`
   exist and default to `[]`.
2. `PATCH /admin/universities/{id}` with `{"ranking": 5}` — confirm the
   response's `admin_locked_fields` includes `"ranking"`.
3. Run `python scripts/backfill_ranking_from_label.py` locally against that
   same row — confirm it logs a skip for that university and `ranking`
   stays `5` (not reverted to the label-parsed value).
4. Same check for a `Program` field: PATCH a program's `description`, then
   run `python scripts/seed_kz_universities.py` and confirm the
   description survives and a skip line is logged for that program.
5. Confirm an *unlocked* university/program is still updated normally by
   these scripts (regression check — the lock must be opt-in per field, not
   accidentally blocking everything).
