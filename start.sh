#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

docker compose up -d --build
docker compose restart nginx
docker compose exec api alembic upgrade head

echo "Backend is ready: http://localhost/docs"

#docker-compose exec api python scripts/seed_questions.py
# Ожидается: Total questions in bank: 102
# Команда нужна для того что прогнать скрипт по вопросам 