#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# University photos are served by nginx straight from a host folder (no MinIO).
# docker-compose.yml bind-mounts ${MEDIA_DIR:-../profy-media} at /srv/media in
# both api and nginx. The folder is NOT in git — get profy-media.tar.gz from
# the team share and extract it next to this repo (so ../profy-media/universities/
# has the <slug>.webp files), or rebuild it: scripts/export_university_photos.py
# then scripts/generate_card_thumbnails.py.
#
# Missing folder is not fatal — the backend runs fine, university cards just
# show the placeholder icon instead of a photo. We create the dir so Docker
# doesn't auto-make it as root.
MEDIA_DIR="${MEDIA_DIR:-../profy-media}"
export MEDIA_DIR
mkdir -p "$MEDIA_DIR/universities"
if [ -z "$(find "$MEDIA_DIR/universities" -maxdepth 1 -name '*.webp' -print -quit 2>/dev/null)" ]; then
  echo "WARNING: no photos in '$MEDIA_DIR/universities' — cards will show the placeholder icon."
  echo "         Get profy-media.tar.gz from the team share, or run"
  echo "         scripts/export_university_photos.py + scripts/generate_card_thumbnails.py."
fi

# --remove-orphans clears the old minio / minio-init containers on machines
# that ran the pre-filesystem stack.
docker compose up -d --build --remove-orphans
docker compose restart nginx

# Wait for the api container to actually accept connections before the first
# `exec` — `up -d --build` returns as soon as the container is *started*, not
# ready, and a rebuild makes it recreate mid-script (cd.yml has the same loop).
echo "Waiting for api..."
for i in $(seq 1 60); do
  if docker compose exec -T api python -c "import socket; s=socket.socket(); s.settimeout(1); s.connect(('127.0.0.1', 8000)); s.close()" >/dev/null 2>&1; then
    break
  fi
  [ "$i" -eq 60 ] && { echo "ERROR: api did not become ready in 60s"; docker compose logs api | tail -40; exit 1; }
  sleep 1
done

docker compose exec api alembic upgrade head

echo "Backend is ready: http://localhost/docs"

# Photo-serving smoke check — diagnostic only, must never abort the script
# (set -euo pipefail is unforgiving of SIGPIPE from `ls | head`, curl, grep).
set +e
{
  _photo_file=$(find "$MEDIA_DIR/universities" -maxdepth 1 -name '*.webp' -print -quit 2>/dev/null)
  if [ -n "$_photo_file" ]; then
    _photo_slug=$(basename "$_photo_file" .webp)
    _code=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost/media/universities/${_photo_slug}.webp")
    echo "Photo check: GET /media/universities/${_photo_slug}.webp -> HTTP ${_code} (expect 200)"
    _api=$(curl -s "http://localhost/api/v1/universities/programs?profession=arhitektor&limit=1" \
      | grep -o '"image_url":"[^"]*"' | head -1)
    echo "Photo check: API image_url -> ${_api:-<none>}"
  else
    echo "Photo check: '$MEDIA_DIR/universities' has no *.webp — build it with scripts/export_university_photos.py"
  fi
}
set -e

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

# --- university-cards-ux-fix-plan.md fixes (2026-08-19) ---
# NOTE: unlike the seed scripts above, these all default to a DRY RUN —
# `--apply` is required to actually write. Don't drop the flag when adding a
# new one here, or a fresh reseed will silently skip it.
#
# ranking/ranking_label (§1) and Program.cost_label/requirements["notes"]
# (the notes/cost split) used to only get set at creation time in
# seed_92_professions_universities.py, so a row seeded before a CLUSTERS
# correction (or before parse_ranking()/the notes-splitting bug were fixed)
# kept a stale value forever — that seed script now re-derives all of these
# on every run for existing rows too, so correcting CLUSTERS data is enough
# on its own; no separate backfill scripts needed any more. Same for
# Program.description on KZ bulk-seeded programs (§7, was defaulting to the
# specialty-group category label) — seed_kz_universities.py's existing
# generic per-field diff already re-derives it (null) on every run, covering
# both the main source data and the KazATU duplicate-record rows that used
# to need their own separate backfill.

# Real, source-verified academic program names (§5) — replaces
# seed_92_professions_universities.py's program_name = direction.name bug
# and the separate ЕНУ/КазАТУ faculty-name bug, for every cluster/university
# researched so far. Reviewed data in scripts/data/specialty_name_review_cluster_*.json
# (committed); entries flagged needs_manual_review are intentionally skipped.
# Only covers clusters 0,1,2,3,4,6,8,9,10 so far — 5,7,11 and the rest of 12
# are still open, see university-cards-ux-fix-plan.md §5.
docker-compose exec api python scripts/apply_specialty_names_from_review.py --apply
docker-compose exec api python scripts/fix_enu_kazatu_program_names.py --apply


# Real institutional descriptions for KZ universities, replacing the
# "N программ на M факультетах" placeholder (§7 follow-up) — reviewed data
# hardcoded in the script (51 universities researched so far, of 111 total).
docker-compose exec api python scripts/apply_university_descriptions_batch1.py --apply


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
# NOTE: the photo-import scripts (scripts/import_jinaq_university_photos.py,
# scripts/apply_*_photos_from_wikidata.py, scripts/import_manual_university_photos.py)
# are intentionally NOT run here — together they pull ~2300 images over the
# network (~15 min) and are a one-time job, not a per-deploy step. Photos are
# served by nginx from ${MEDIA_DIR:-../profy-media} (STORAGE_BACKEND=fs); to move
# them to a server, copy that folder (tar + scp) rather than re-downloading.
# See app/integrations/storage/ for the backend.

# Most KZ universities jinaq couldn't exact-match already existed in the
# curated set under a different name string (abbreviations, "имени"/"им.",
# EN/RU name pairs, institution renames, Astana/Nur-Sultan city naming) —
# checked by hand, reviewed in scripts/data/jinaq/kz_university_merge_review.json.
# Merges each confirmed jinaq duplicate's photo/specialties into the curated
# row and deletes the duplicate. Idempotent (already-merged entries are a
# no-op), local dataset, no network access.
docker-compose exec api python scripts/apply_kz_university_merge.py
# Pre-existing duplicate unrelated to jinaq: KAZGUU University was renamed
# to Maqsut Narikbayev University, but both the old (kazgyuu) and new (mnu)
# rows existed separately in the curated dataset. Idempotent, no-op once merged.
docker-compose exec api python scripts/merge_kazguu_into_mnu.py

# Tags Program rows (mostly the jinaq import above, but any other untagged
# program too) with directions/professions from the human-reviewed mapping
# in scripts/data/jinaq/specialty_direction_review.json. Only ever touches
# rows with zero directions so far — never overwrites specialty_profession_map.py's
# curated tagging. Idempotent, local dataset, no network access.
docker-compose exec api python scripts/apply_jinaq_specialty_directions.py

# Hand-researched admission profiles (hybrid ЕНТ+own-test vs no-ЕНТ-at-all)
# for KZ universities without an ovpo_code, so apply_grant_admission_data_2026.py
# has nothing to key off for them — reviewed data in
# scripts/data/researched_kz_admission_data.json (committed). Idempotent,
# keyed by a hand-checked slug map in the script itself.
docker-compose exec api python scripts/apply_researched_kz_admission_data.py
# Foreign-university duplicates surfaced while world-ranking every university
# (same institution under two name strings, or one row with a wrong/generic
# city inherited from an old superseded seed script) — reviewed pairs in
# scripts/data/foreign_university_dedup_review.json (committed). Idempotent,
# keyed by university_id; a re-run after a completed merge is a no-op.
docker-compose exec api python scripts/apply_foreign_university_dedup.py
# UNIRANKS 2027 world rank (not the per-country table used for Kazakhstan
# above) for every university uniranks.com actually rates — reviewed data in
# scripts/data/uniranks_world_rank_review.json (committed, gathered via
# generate_uniranks_world_rank_review.py's live per-university lookups, which
# needs network access and is NOT run here). Idempotent, keyed by university_id.
docker-compose exec api python scripts/apply_uniranks_world_rank.py