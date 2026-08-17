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
# 2026-2027 grant/ENT-threshold admission data into Program.requirements —
# reviewed data from scripts/data/db_updates_2026.json (committed). Idempotent,
# keyed by program_id, so it must run after seed_kz_universities.py.
docker-compose exec api python scripts/apply_grant_admission_data_2026.py
docker-compose exec api python scripts/backfill_program_source_metadata_2026.py