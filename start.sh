#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

docker compose up -d --build
docker compose restart nginx
docker compose exec api alembic upgrade head

echo "Backend is ready: http://localhost/docs"

# Question banks — order matters: bigfive/mi/question_pairs each resolve
# `order`/name references against whatever was seeded before them.
docker-compose exec api python scripts/seed_riasec_questions.py
# Ожидается: Total questions in bank: 146
docker-compose exec api python scripts/seed_bigfive_questions.py
# Ожидается: Total questions in bank: 120
docker-compose exec api python scripts/seed_mi_questions.py
# Ожидается: Total questions in bank: 48
docker-compose exec api python scripts/seed_question_pairs.py
# Ожидается: Total pairs in bank: 67

# Motivation block (senior triplets + junior/middle Harter pairs)
docker-compose exec api python scripts/seed_motivation_statements.py
docker-compose exec api python scripts/seed_motivation_pairs.py
# Ожидается: Total pairs in bank: 18

docker-compose exec api python scripts/seed_riasec_directions.py
# Direction description/skills_needed/subjects_to_develop/first_steps — empty
# by default after the RIASEC migration (see app/models/direction.py).
# Content already LLM-drafted and human-reviewed into
# scripts/direction_content_review.json (committed) — this only applies that
# reviewed file, it does not call the LLM. Idempotent, needs directions'
# slugs to already exist, so it must run after seed_riasec_directions.py.
docker-compose exec api python scripts/apply_direction_content.py

# Universities/programs — single source of truth: university-data/*.py
# (Almaty + Astana + the 48 regional/branch universities from
# missing_kz_universities_data.py, 103 real KZ universities total) via
# specialty_profession_map.py. seed_universities.py (12 hand-picked,
# duplicate logic) was removed.
docker-compose exec api python scripts/seed_kz_universities.py
# 92-profession cluster report ("Университеты для 92 профессий.txt") — 1 KZ
# regional university + up to 13 world universities per cluster (expanded
# 2026-08-19, was 3-4), one Program per (university, profession) pair.
# Idempotent, keyed by (university slug) / (university_id, program name);
# reviewed data in scripts/data/universities_92_professions.py (committed).
docker-compose exec api python scripts/seed_92_professions_universities.py
# The script above used to smash cost + admission-requirements text into one
# Program.requirements["notes"] string (and as a bare string, not list[str] —
# university_requirements.py does `list(requirements.get("notes") or [])`,
# which explodes a bare string into one character per list entry). Both bugs
# are fixed in the seed script itself now; this backfills rows created before
# the fix, splitting cost into Program.cost_label and leaving notes clean.
# No-op on a fresh DB, safe/idempotent to keep running.
docker-compose exec api python scripts/backfill_program_cost_label_2027.py
# UNIRANKS® 2027 Kazakhstan ranking (kz_rank/world_rank, or "Н/Р" where
# checked and confirmed absent from the ranking) — reviewed data from
# scripts/data/uniranks_kz_2027.json (committed). Idempotent, keyed by slug;
# covers universities from both seed scripts above (e.g. kartu-karaganda,
# toraigyrov-university come from seed_92_professions_universities.py), so it
# must run after both, not just after seed_kz_universities.py.
docker-compose exec api python scripts/apply_uniranks_kz_2027.py
docker-compose exec api python scripts/apply_uniranks_not_ranked.py
# website/location/short_name for the universities seed_92_professions_universities.py
# doesn't populate (foreign + KZ-regional cluster universities) — reviewed
# data from scripts/data/university_enrichment_2027.json (committed).
# Idempotent, keyed by slug, so it must run after seed_92_professions_universities.py.
docker-compose exec api python scripts/apply_university_enrichment_2027.py
# exams/needs_portfolio/needs_essay/needs_recommendations/needs_interview,
# extracted via LLM from the free-text admission-requirements notes seeded by
# seed_92_professions_universities.py (a human reviewed the draft before this
# was committed — see generate_program_requirements_content.py's docstring).
# Idempotent, keyed by program_id; reviewed data in
# scripts/program_requirements_review_2027.json (committed).
docker-compose exec api python scripts/apply_program_requirements_content_2027.py
# 2026-2027 grant/ENT-threshold admission data into Program.requirements —
# reviewed data from scripts/data/db_updates_2026.json (committed). Idempotent,
# keyed by program_id, so it must run after seed_kz_universities.py.
docker-compose exec api python scripts/apply_grant_admission_data_2026.py
docker-compose exec api python scripts/backfill_program_source_metadata_2026.py

# ovpo_code — canonical MES RK grant-registry key (A1), replaces name-based
# matching; also merges 2 confirmed duplicate University rows. Idempotent,
# keyed by slug — must run after both seed scripts above.
docker-compose exec api python scripts/apply_ovpo_codes.py
# One-time dedup for Program rows created identically by two different seed
# pipelines (e.g. "Биология" vs "Биология (бакалавр)") — needed before the
# (university_id, name_normalized) unique index can hold on a reseed. No-op
# once already merged.
docker-compose exec api python scripts/merge_duplicate_programs.py
# Numeric ranking backfill for QS/THE World labels the seed script's regex
# didn't parse before the A5 fix (national/subject-specific labels stay NULL
# on purpose — see script docstring).
docker-compose exec api python scripts/backfill_world_ranking.py
# Numeric cost_per_year_min/max/currency from cost_label text (A6) —
# conservative parser, only fills unambiguous single-figure labels.
docker-compose exec api python scripts/backfill_cost_range.py

# --- university-cards-ux-fix-plan.md fixes (2026-08-19) ---
# NOTE: unlike the backfill scripts above, these all default to a DRY RUN —
# `--apply` is required to actually write. Don't drop the flag when adding a
# new one here, or a fresh reseed will silently skip it.

# University.ranking must only ever hold a genuine QS World figure, never a
# subject/national/US-News number from the same free-text label (§1) — the
# parser itself is already fixed in seed_92_professions_universities.py, so
# this only re-derives `ranking` for rows already seeded before that fix.
docker-compose exec api python scripts/backfill_ranking_from_label.py --apply

# Program.description for KZ bulk-seeded programs must never be the
# specialty-group category label (§7) — seed_kz_universities.py itself is
# already fixed (writes null now), this re-derives rows seeded before that.
docker-compose exec api python scripts/backfill_kz_program_description.py --apply
# Same bug, but for the 14 KazATU programs seeded from the duplicate
# "kazahskij-agrotehnicheskij-universitet-kazatu" record in
# almaty_universities_data.py that backfill_kz_program_description.py's
# _find_university() can't resolve (see docs/university-module-fix-plan.md A1
# and this script's own docstring).
docker-compose exec api python scripts/backfill_kazatu_duplicate_group_labels.py --apply

# Real, source-verified academic program names (§5) — replaces
# seed_92_professions_universities.py's program_name = direction.name bug
# and the separate ЕНУ/КазАТУ faculty-name bug, for every cluster/university
# researched so far. Reviewed data in scripts/data/specialty_name_review_cluster_*.json
# (committed); entries flagged needs_manual_review are intentionally skipped.
# Only covers clusters 0,1,2,3,4,6,8,9,10 so far — 5,7,11 and the rest of 12
# are still open, see university-cards-ux-fix-plan.md §5.
docker-compose exec api python scripts/apply_specialty_names_from_review.py --apply
docker-compose exec api python scripts/fix_enu_kazatu_program_names.py --apply

# Foreign-university cost_label text must never show a master's-only or
# domestic/subsidized-citizen rate to a KZ bachelor's applicant (§2) —
# reviewed rules hardcoded in the script itself (small, fixed, per-university
# set), not a separate JSON file.
docker-compose exec api python scripts/backfill_strip_masters_domestic_cost.py --apply

# Real institutional descriptions for KZ universities, replacing the
# "N программ на M факультетах" placeholder (§7 follow-up) — reviewed data
# hardcoded in the script (51 universities researched so far, of 111 total).
docker-compose exec api python scripts/apply_university_descriptions_batch1.py --apply

# Foreign-university cost_label was 100% free text before this (0/1205 had a
# numeric cost_per_year) — inconsistent currencies/formats on the card, and
# several texts showed a domestic/citizen-only rate a KZ applicant can't
# actually get (e.g. Tsinghua "для китайцев", Tokyo "бесплатно для японцев";
# §2/§10). Sets cost_per_year_min/max/currency directly from a hand-read
# international-applicable figure for 148 distinct cost_label texts (1016 of
# 1205 programs) — the existing convert_cost_to_usd validator
# (app/schemas/university.py) does the currency conversion at read time, so
# once this runs there's no free-text parsing left for those rows at all.
# Two passes: the second catches (university, label) pairs the first missed
# because the same label text is shared by a university under two slightly
# different name strings.
docker-compose exec api python scripts/backfill_foreign_cost_numeric.py --apply
docker-compose exec api python scripts/backfill_foreign_cost_numeric_pass2.py --apply

# ЕНТ profile-subject pairs (§8-9) — replaces per-university website-sourced
# pairs with the OFFICIAL state classifier (Приложение 1 к Правилам
# проведения ЕНТ), keyed by platform profession, not by program text
# matching (avoids the specialty-name -> classifier-code cross-reference
# problem entirely). Covers 88 of 92 professions with a confident mapping;
# 4 generic ones (school teacher, university lecturer, secretary, civil
# servant) are deliberately left untouched — see script docstring. Only
# subjects, not the grant-threshold scores (a separate, harder problem).
docker-compose exec api python scripts/apply_ent_profile_subjects.py --apply

# jinaq world university directory (2313 universities / 32 countries, 10,113
# majors) — committed dataset in scripts/data/jinaq/universities.json, no
# network access needed, ~30s. Idempotent: links to existing rows by exact
# (name, city, country) match or creates new ones, upserts programs, never
# touches price. See script docstring for the full rationale.
docker-compose exec api python scripts/import_jinaq_universities.py
# One-time correction for Program rows created by an earlier version of the
# import script above, which dumped enrollmentRequirements AND
# enrollmentDocuments into the same `requirements.notes` — jinaq's own data
# restates the same admission facts in both lists for most foreign
# universities, so that read as literal duplication on the program-detail
# page. The import script itself is already fixed; this only repairs rows
# created before the fix. No-op on a fresh DB, safe/idempotent to keep running.
docker-compose exec api python scripts/backfill_jinaq_program_requirements.py
# NOTE: scripts/import_jinaq_university_photos.py is intentionally NOT run
# here — it downloads ~2300 images from the real jinaq.ai over the network
# (~15 min) and is a one-time job, not a per-deploy step. Run it manually
# once locally, then mirror the resulting MinIO bucket to prod storage
# (`mc mirror local/profi-media prod/profi-media`) instead of re-downloading.

# Most KZ universities jinaq couldn't exact-match already existed in the
# curated set under a different name string (abbreviations, "имени"/"им.",
# EN/RU name pairs, institution renames, Astana/Nur-Sultan city naming) —
# checked by hand, reviewed in scripts/data/jinaq/kz_university_merge_review.json.
# Merges each confirmed jinaq duplicate's photo/specialties into the curated
# row and deletes the duplicate. Idempotent (already-merged entries are a
# no-op), local dataset, no network access.
docker-compose exec api python scripts/apply_kz_university_merge.py

# Tags Program rows (mostly the jinaq import above, but any other untagged
# program too) with directions/professions from the human-reviewed mapping
# in scripts/data/jinaq/specialty_direction_review.json. Only ever touches
# rows with zero directions so far — never overwrites specialty_profession_map.py's
# curated tagging. Idempotent, local dataset, no network access.
docker-compose exec api python scripts/apply_jinaq_specialty_directions.py