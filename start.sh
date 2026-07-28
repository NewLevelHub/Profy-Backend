#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

docker compose up -d --build
docker compose restart nginx
docker compose exec api alembic upgrade head

echo "Backend is ready: http://localhost/docs"

# Akinator taxonomy first — universities/simulations reference its direction slugs
docker compose exec api python scripts/seed_akinator_content.py
docker compose exec api python scripts/seed_simulations.py
docker compose exec api python scripts/seed_subject_questions.py
docker compose exec api python scripts/seed_universities.py
docker compose exec api python scripts/seed_astana_universities.py
docker compose exec api python scripts/seed_almaty_universities.py
