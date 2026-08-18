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
# (Almaty + Astana, 55 real KZ universities) via specialty_profession_map.py.
# seed_universities.py (12 hand-picked, duplicate logic) was removed.
docker-compose exec api python scripts/seed_kz_universities.py
# 92-profession cluster report ("Университеты для 92 профессий.txt") — 1 KZ
# regional university + 3-4 world universities per cluster, one Program per
# (university, profession) pair. Idempotent, keyed by (university slug) /
# (university_id, program name); reviewed data in
# scripts/data/universities_92_professions.py (committed).
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