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
docker-compose exec api python scripts/seed_lie_scale_questions.py
# Ожидается: Total validity items in banks: 25 (20 MC-SDS + 5 infrequency)
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

# ─────────────────────────────────────────────────────────────────────────────
# Universities / programs — ONE committed file, ONE loader.
#
# scripts/data/university_snapshot.clean.json is the single source of truth:
# ~2400 universities, ~12400 programs, profession tags and world_rank (UNIRANKS
# Global Rank) all baked in. It is rebuilt OFFLINE by
# `python scripts/build_catalog.py` (export → normalize/dedup → world-rank →
# canonical slugs → profession tags) from the committed raw dump + review/map
# files — nothing here touches the network.
#
# build_universities.py replaces the whole old ~30-script pipeline
# (seed_kz_universities, seed_92_professions_universities, import_jinaq_*,
# every apply_* / backfill_* / merge_*). Deterministic uuid5 ids, so the same
# row has the same id on every DB. On a DB seeded the old way it does a
# one-time destructive rebuild (prune every random-uuid row, insert fresh);
# on every later run it is a near no-op.
#
# Requires `directions` seeded above (profession tags resolve by Direction slug).
docker compose exec api python scripts/build_universities.py

# University photo files are named by the pre-canonicalization slugs; the
# dedup + canonical-slug pass renamed ~220 university slugs. Rename the
# matching <slug>.webp / <slug>.card.webp (from scripts/data/slug_rename_map.json
# + scripts/data/photo_alias_map.json) so photos still resolve. Idempotent —
# already-renamed files are skipped; no-op if the media folder is absent.
# Run on the HOST (pure-stdlib script) against the host media folder — avoids
# the container-path / MSYS-path-mangling issues of `docker compose exec`.
if [ -n "$(find "$MEDIA_DIR/universities" -maxdepth 1 -name '*.webp' -print -quit 2>/dev/null)" ]; then
  _py="${PYTHON:-}"
  [ -z "$_py" ] && { command -v python3 >/dev/null 2>&1 && _py=python3 || _py=python; }
  "$_py" scripts/rename_university_photos.py --media-dir "$MEDIA_DIR" --apply
fi