# Content-pipeline row-ID resolution audit (PRO-244 / PRO-246)

Branch `pro-244` is based on `origin/dev`. The `pro-227` branch made an
overlapping fix to `apply_kz_university_merge.py` (plus admin-lock guards on
several apply scripts); it is not in `dev`, so `pro-244` re-does the
`apply_kz_university_merge.py` fix through `scripts/entity_resolver.py` and
does **not** carry the admin-lock (`is_locked`) guards. When `pro-227`
merges, `apply_kz_university_merge.py` / `apply_uniranks_world_rank.py` /
`apply_foreign_university_dedup.py` will conflict — combine the two
(resolver-based resolution here + `is_locked` guards there).

## The problem

`University.id` and `Program.id` are `uuid.uuid4()` primary keys, assigned
independently per row per database (`app/models/university.py`,
`app/models/program.py`). `import_jinaq_universities.py` and the university
seed scripts never set `id` explicitly, so the same real institution gets a
different UUID on every separately-seeded database — a developer's local
copy, the dev stack, prod on its first pipeline run.

A one-off script that matches a `University`/`Program` row by a UUID
hardcoded into a checked-in review/data file therefore resolves nothing on
any database other than the one that file was generated against. The script
does not error — it logs `not found` / `already done` per entry and exits 0
— so the failure is silent: the intended change is simply never applied.

Confirmed live on the local DB:

| script | result |
|---|---|
| `apply_uniranks_world_rank.py` | `updated: 0, skipped (not found): 1364` of 1364 confirmed |
| `apply_foreign_university_dedup.py` | `UNRESOLVED (stale review data): 22` of 22 confirmed pairs |

## The fix

Resolve rows by a cross-DB-portable key, via `scripts/entity_resolver.py`:

- **University** — `jinaq_external_id` (through `university_external_refs`,
  `source="jinaq"`, written on every import regardless of DB) → `slug`
  (unique, the de-facto key for curated rows) → `ror_id` (canonical foreign
  dedup key, sparsely populated). `resolve_university(...)` /
  `resolve_jinaq_university(...)`.
- **Program** — its parent University (by the keys above) plus the
  degree-suffix-normalized program *name*, which backs the
  `(university_id, name_normalized)` unique constraint.
  `resolve_program(...)`.

Enforced going forward by `tests/unit/test_review_files_portable_keys.py`:
every record in `scripts/data/**/*.json` / `scripts/*review*.json` that
references a row must carry a portable key. Non-compliant files are
allowlisted there with the ticket that fixes them.

## Rejected alternative — deterministic `uuid5` primary keys

Making `import_jinaq_universities.py` assign
`id = uuid5(NAMESPACE_URL, f"jinaq:{external_id}")` was considered and
rejected as the primary fix:

- It fixes only the jinaq subset. Curated rows (`university-data/*.py`,
  `seed_universities.py`) still get `uuid4()` and still need `slug`. The
  `uniranks_world_rank_review.json` universities and half of the
  `foreign_university_dedup_review.json` pairs are curated/foreign — a
  jinaq-only scheme fixes none of PRO-245.
- `university_external_refs` (unique `(source, external_id)`) already
  provides a cross-DB-stable jinaq identity, and
  `apply_kz_university_merge.py` already consumes it. Deterministic PKs
  would be a redundant second mechanism.
- Retrofitting on prod means rewriting the PK of every jinaq `University`
  row, FK-referenced by `programs`, `university_images`,
  `university_external_refs`, certificates, `program_directions` (via
  programs) and admin edit-lock rows — a coordinated multi-table cascade
  for no gain over repointing refs.

Worth a separate hardening ticket only if a static file authored offline
(no DB round-trip) ever needs to reference a jinaq `University`.

## Script-by-script audit

Every `scripts/*.py` that reads `scripts/data/**` (or a `scripts/*review*.json`)
and/or matches `University`/`Program` by `id`.

### Broken / affected

| script | in `cd.yml` | how it matches | disposition |
|---|---|---|---|
| `apply_kz_university_merge.py` | **yes** (`cd.yml:215`, `start.sh:215`) | `db.get(University, uuid.UUID(entry["jinaq_university_id"]))` — the stale per-DB snapshot | **Fixed** (was fixed in `pro-227`; re-done here for the `dev` base). Resolves the jinaq row via `resolve_jinaq_university(entry["jinaq_external_id"])`, repoints the ref with `repoint_jinaq_ref` after a merge, treats `jinaq_uni.id == target.id` as "already done". |
| `apply_uniranks_world_rank.py` | no | `University.id == entry["university_id"]` from `data/uniranks_world_rank_review.json` (1371 records, no portable key) | **PRO-245** — generator emits `slug`/`jinaq_external_id`/`ror_id`; one-time `enrich_uniranks_world_rank_review_keys.py` backfills the existing file from the authoring DB; apply script switches to `resolve_university` |
| `apply_foreign_university_dedup.py` | no | `University.id` for both `keep` and `remove` from `data/foreign_university_dedup_review.json` (22 pairs; only a combined `name` string, no portable key) | **PRO-247** — new `generate_foreign_university_dedup_review.py` re-derives pairs on the target DB with `slug`/`ror_id` per side + everything a human needs to re-confirm; apply script resolves by `keep_slug`/`remove_slug` |
| `backfill_program_source_metadata_2026.py` | **yes** (`cd.yml:188`) | `Program.id == program_id` where `program_id` is the dict *key* in `data/db_updates_2026.json` (513 entries; each value already carries `slug` + `name`, used only for logging) | **PRO-246 (this ticket)** — resolve via `resolve_program(resolve_university(slug=payload["slug"]), payload["name"])`. No data-file change needed. See "Fix applied" below. |
| `apply_program_requirements_content_2027.py` | **yes** (`cd.yml:186`) | `Program.id` for each id in `group["program_ids"]` from `program_requirements_review_2027.json` (130 groups). Group has `university_slug` but **no per-program name**, and `program_ids` is a *subset* of the university's programs (grouped by `(university_id, notes_text)`) | **Separate follow-up ticket.** Needs the generator (`generate_program_requirements_content.py`) changed to emit `programs: [{name, id}]` instead of `program_ids: [id]`, which means re-running an LLM pass. Allowlisted in the guardrail test until then. |
| `fix_enu_kazatu_program_names.py` | **yes** (`cd.yml:197`, `start.sh:167`, both `--apply`) | *was* `db.get(Program, uuid)` for inline UUID literals in `RENAMES` + `SPLIT_SOURCE_PROGRAM_ID` | **Fixed.** It runs on every fresh environment, where those UUIDs match nothing, so the ЕНУ/КазАТУ rename silently never applied. `RENAMES` is now `(university_slug, old_name, new_name)` and both the renames and the split resolve via `resolve_program(resolve_university(slug), name)`. Runs before the jinaq import / merge, so `enu` / `kazatu` are still single rows at that point. |

### Safe — already resolve by a portable key or a live query

| script | resolves by |
|---|---|
| `apply_ovpo_codes.py` | `University.slug` (live `select … where slug in (…)`); inline `MATCHED` dict is slug-keyed; docstring records that a fuzzy-match pass was discarded for false positives |
| `merge_duplicate_programs.py` | live `select(Program)` grouped by `(university_id, normalize(name))` from live rows — no hardcoded id |
| `merge_kazatu_duplicate.py`, `merge_kazguu_into_mnu.py` | `University.slug` (hardcoded slug constants, no data file) |
| `generate_kz_university_merge_review.py` | emits both `jinaq_external_id` (portable) and `jinaq_university_id` (snapshot); consumer uses the former |
| `import_jinaq_universities.py` | `university_external_refs` first, then normalized `(name, city, country)` |
| `apply_grant_admission_data_2026.py` | live KZ-program query; `MIN_ENT_THRESHOLD_OVERRIDES` is a string-`program_id`-keyed override lookup — a harmless off-DB no-op, cosmetic only |
| `apply_uniranks_kz_2027.py`, `apply_university_enrichment_2027.py`, `apply_researched_kz_admission_data.py`, `apply_specialty_names_from_review.py` | `University.slug` — their review files are slug-keyed |
| photo-review scripts (`foreign_university_photo_review.json`, `missing_university_photo_review.json` + wikidata appliers) | carry `university_slug` alongside `university_id`; resolve by slug / jinaq ref |

## Full `start.sh` / `cd.yml` sweep

`start.sh` is the local bootstrap and mirrors the `cd.yml` deploy step
order. Every script it invokes was checked so a fresh run produces the same
result on any environment. Beyond the seed/bank scripts (keyed by their
bank-file key) and everything in the tables above:

| script | resolves by | verdict |
|---|---|---|
| `apply_direction_content.py` | `Direction.slug` (`by_slug[entry["slug"]]`) | safe |
| `seed_92_professions_universities.py` | University by `ror_id` → `slug`; Program by `(university.id, name)` from the live row | safe |
| `apply_uniranks_not_ranked.py` | `University.slug` from `NOT_RANKED_SLUGS` | safe |
| `apply_grant_admission_data_2026.py` | live `select(Program).join(University).where(country == "Казахстан")`; `MIN_ENT_THRESHOLD_OVERRIDES` is a string-`program_id` override lookup that returns the default when absent — harmless off its authoring DB | safe (override dict cosmetic) |
| `backfill_world_ranking.py` | live `select(University).where(ranking IS NULL, ranking_label IS NOT NULL)` | safe |
| `apply_university_descriptions_batch1.py` | `University.slug.in_(UPDATES.keys())`, `UPDATES` slug-keyed, guarded on `description` | safe |
| `apply_ent_profile_subjects.py` | `Direction.slug` (`SUBJECT_PAIRS` slug-keyed), live join to KZ programs | safe |
| `apply_jinaq_specialty_directions.py` | normalized program name against the review map + `direction_by_slug` | safe |
| `backfill_jinaq_program_requirements.py` | `university_external_refs` (`source="jinaq"`) | safe |
| `merge_kazguu_into_mnu.py` | `University.slug` constants | safe |

**Conclusion:** after the fixes above, no script in `start.sh` / `cd.yml`
resolves a `University`/`Program` by a bare per-DB UUID. The four that
carried a stale hardcoded id (`apply_kz_university_merge.py`,
`apply_uniranks_world_rank.py`, `apply_foreign_university_dedup.py`,
`fix_enu_kazatu_program_names.py`) and the two dict-keyed-by-id files
(`backfill_program_source_metadata_2026.py` fixed here,
`apply_program_requirements_content_2027.py` in a follow-up) are the
complete set.

### `start.sh` prerequisite: commit the regenerated review files

`start.sh` reads the **committed** `scripts/data/*.json`. For the two
fixed apply scripts to actually do their work on a fresh checkout, the
regenerated files must be committed:

- `scripts/data/uniranks_world_rank_review.json` — after
  `enrich_uniranks_world_rank_review_keys.py` has added `slug` /
  `jinaq_external_id` to every record.
- `scripts/data/foreign_university_dedup_review.json` — regenerated by
  `generate_foreign_university_dedup_review.py` and re-confirmed
  (`keep_slug` / `remove_slug` per pair).

Until then those two scripts run clean but change nothing (they log
`skipped (no portable key)` / `UNRESOLVED … regenerate`), which is the
correct fail-safe, not a silent wrong result.

## Fix applied in PRO-246: `backfill_program_source_metadata_2026.py`

`data/db_updates_2026.json` is a dict keyed by a snapshot `Program.id`;
every value already carries `slug` (university slug) + `name` (program
name), previously used only in log strings. No file rewrite needed.

- Per entry: skip if the payload lacks `slug` or `name`
  (`skipped_no_key`).
- `uni, _ = resolve_university(db, slug=payload["slug"])` → `missing` if None.
- `program = resolve_program(db, university=uni, name=payload["name"])` →
  `missing` if None. Maps onto `(university_id, name_normalized)` → at most
  one row.
- Unchanged: the `program.updated_at is not None → skip` guard, the
  `source_url` derivation, `--dry-run`.

**Prod behaviour change:** today this script no-ops on prod (the snapshot
UUIDs match nothing). After the fix it will set `source_url` + `updated_at`
on the `programs` rows with `updated_at IS NULL` that the 2026 grant pass
touched — which is its stated purpose, but it is a real first-run data
write. Run it manually with `--dry-run` on prod and eyeball the count + a
sample before the deploy that ships this.

On the local DB the fixed `--dry-run` reports `updated: 376, missing: 137`
(was `0` / `513` — all snapshot ids dead). Every one of the 137 misses is a
whole university whose `slug` in the file no longer exists on that DB
(`kazgyuu` → merged into `mnu` by `merge_kazguu_into_mnu.py`,
`al-farabi-kazakh-national-university`, etc.) — slug drift from the
manually-run one-off merge scripts, not a name-matching failure (once a
university resolves, its program name resolves 376/376). A prod DB that
hasn't had those manual merges applied will resolve more; the `missing`
list names every unresolved university so the gap is visible, not silent.
