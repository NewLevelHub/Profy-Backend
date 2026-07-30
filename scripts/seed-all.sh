#!/usr/bin/env bash
# Run all idempotent seed scripts inside the API container.
#
# Local dev (default):
#   ./scripts/seed-all.sh
#
# Remote dev server (compose project profy-dev):
#   ./scripts/seed-all.sh dev
#
# Production:
#   ./scripts/seed-all.sh prod
#
# Direct container name (no compose):
#   ./scripts/seed-all.sh container profi_api_dev
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

TARGET="${1:-local}"
SERVICE="api"
COMPOSE_FILE="docker-compose.yml"
ENV_FILE=""
COMPOSE_PROJECT=()
EXEC_PREFIX=(docker compose exec -T)

case "$TARGET" in
  local)
    ;;
  dev)
    COMPOSE_FILE="docker-compose.dev.yml"
    ENV_FILE=".env.development"
    SERVICE="api_dev"
    COMPOSE_PROJECT=(-p profy-dev)
    ;;
  prod)
    COMPOSE_FILE="docker-compose.prod.yml"
    ENV_FILE=".env.production"
    SERVICE="api"
    ;;
  container)
    CONTAINER="${2:?container name required, e.g. profi_api_dev}"
    EXEC_PREFIX=(docker exec "$CONTAINER")
    SERVICE=""
    ;;
  *)
    echo "Usage: $0 [local|dev|prod|container <name>]" >&2
    exit 1
    ;;
esac

run_seed() {
  local script="$1"
  echo "==> $script"
  if [[ -n "$SERVICE" ]]; then
    if [[ -n "$ENV_FILE" ]]; then
      docker compose "${COMPOSE_PROJECT[@]}" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" \
        exec -T "$SERVICE" python "scripts/$script"
    else
      docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE" python "scripts/$script"
    fi
  else
    "${EXEC_PREFIX[@]}" python "scripts/$script"
  fi
}

run_seed seed_akinator_content.py
run_seed seed_subject_questions.py
run_seed seed_universities.py
run_seed seed_astana_universities.py
run_seed seed_almaty_universities.py

echo "==> All seed scripts finished"
