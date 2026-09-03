# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Stack

FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL 16 + Redis 7 + Alembic, behind Nginx. Deployed via Docker Compose + GitHub Actions to a VPS.

## Commands

```bash
# Local dev
cp .env.example .env
docker compose up -d --build
docker compose logs -f api

# Migrations (inside the api container)
docker compose exec api alembic upgrade head
docker compose exec api alembic heads          # check before creating a new migration — see Migrations note below

# Seed data (after migrations — see Content pipeline below)
docker compose exec api python scripts/seed_riasec_questions.py
docker compose exec api python scripts/seed_bigfive_questions.py
docker compose exec api python scripts/seed_mi_questions.py
# ... other scripts/seed_*.py and scripts/apply_*.py / backfill_*.py — see
# .github/workflows/cd.yml for the full ordered list run on every deploy

# Tests (need db+redis reachable — e.g. `docker compose up -d db redis` first)
docker compose exec api pytest
docker compose exec api pytest tests/unit/test_riasec_service.py
docker compose exec api pytest tests/unit/test_riasec_service.py::test_name -v
docker compose exec api pytest tests/integration      # integration/ vs unit/
```

There is no CI workflow that runs tests or lint on pull requests — `cd.yml`/`cd-dev.yml` only deploy on push to `main`/`dev`. Running `pytest` locally/in a container before opening a PR is the only automated check that happens.

Before opening a PR, also run `git review-main` (optionally `git review-main high` for a deeper pass) — a local git alias for `scripts/review-before-main.sh`, which runs Claude Code's `/code-review` in headless mode. It picks the diff base to match the two-stage workflow (`feature -> dev`, then `dev -> main`): on `dev` it reviews against `main`; on any other branch it reviews against `dev` (not `main`, which would also include everything already unreleased on `dev`). It excludes `scripts/data/**` and `university-data/**` from the diff (static data dumps, not reviewable logic — they're normally ~97% of a `dev...main` diff's line count and just burn tokens for nothing). The alias itself isn't part of the repo (git aliases live in `.git/config`/`~/.gitconfig`, personal per machine) — set it up once per clone, scoped to this repo only (not `--global`, to avoid clashing with an unrelated `review-main` alias in other repos): `git config alias.review-main '!bash scripts/review-before-main.sh'`.

## Architecture

### Content pipeline: Python "bank" files are the source of truth, not the DB

RIASEC/Big Five/MI questions, forced-choice question pairs, motivation statements/pairs, and RIASEC directions are defined in static Python "bank" files (`scripts/riasec_question_bank.py`, `scripts/bigfive_question_bank.py`, `scripts/motivation_statement_bank.py`, `scripts/motivation_pair_bank.py`, etc.), not edited directly in the DB. The corresponding `scripts/seed_*.py` script is a **self-healing full resync**, run on every CD deploy: it diffs and overwrites the DB row's fields to match the bank, inserts missing rows, and **deletes any DB row whose key is no longer in the bank**. To change this content, edit the bank file and re-run its seed script — do not hand-edit these rows in the DB, a redeploy will revert or delete them. (`University`/`Program` rows are different: seed scripts there only fill currently-empty fields or use narrower overwrite conditions, and never delete rows — see `scripts/seed_kz_universities.py` vs. `scripts/seed_92_professions_universities.py` for the two different patterns in use.)

The CD pipeline (`.github/workflows/cd.yml`, `cd-dev.yml`) runs ~25 of these seed/backfill/apply scripts sequentially after every deploy, in a fixed order — most are idempotent no-ops once their target state is reached, but a few overwrite-if-different rather than fill-if-empty, so re-ordering them or assuming any one is side-effect-free needs checking the individual script.

#### Review/data files must reference rows by a portable key, never a bare row UUID

Any review/data file under `scripts/data/**` (or `scripts/*review*.json`) that points at a `University`/`Program` row MUST carry a cross-DB-portable key — `slug` / `university_slug` (curated rows), `jinaq_external_id` (jinaq rows, resolved via `university_external_refs`), or `ror_id`; a `Program` also needs its *name* to resolve under that University. A bare `University.id` / `Program.id` is a per-database random `uuid4()` and resolves to nothing on any other DB (a fresh local copy, prod's first import run) — the apply script then silently no-ops on every entry. Resolve rows through `scripts/entity_resolver.py` (`resolve_university` / `resolve_program`), not a hand-rolled `where(University.id == ...)`. Enforced by `tests/unit/test_review_files_portable_keys.py`; background and the affected-script audit are in `docs/content-pipeline-id-resolution-audit.md`.

### Assessment: age tiers and multiple instruments

`app/services/age_tiers.py` defines the core visibility rule: a shorter test is a **prefix**, not a separate set — `junior ⊆ middle ⊆ senior` (`visible_tiers()`). Each `Question` row (`app/models/question.py`) carries an `age_tier` and an `instrument` (`riasec` / `big_five` / `mi`) in one shared table. Junior uses MI-style categories instead of RIASEC/Holland codes for its "interests" instrument. Forced-choice `QuestionPair` rows (junior's own screen) and Likert `Question` rows are scored through the same `UserResponse` path — a picked pair choice is written as two synthetic Likert-equivalent responses (see `app/services/question_pair_service.py`), so `riasec_service`/`bigfive_service` scoring doesn't need to know pairs exist.

### Roadmap generation: LLM with template fallback

`app/services/llm_client.py::is_llm_enabled()` gates all LLM calls on `LLM_ENABLED and LLM_API_KEY` — off by default, and the direction/goal roadmap generators fall back to static templates when disabled. The direction roadmap is a much larger generation (4 stages × 2 tracks × 3 tasks) than other LLM calls (inquiry questions, verdicts, report summaries) and uses its own `LLM_ROADMAP_*` timeout/token/model settings — undersizing those truncates the JSON and discards the whole plan.

### Admin endpoints

`app/routers/admin.py` + `app/services/admin_university_service.py` currently expose read + PATCH-only editing for `University`/`Program` (no create/delete). There is no admin editing for question-bank content yet — because of the resync behavior above, adding it isn't a plain PATCH; see `docs/admin-edit-lock-plan.md` and `docs/admin-questions-content-overrides-plan.md` for the planned approach before building anything in this area.

### Deploy topology (relevant when touching docker-compose/nginx)

Three separate environments — local (`docker-compose.yml`), a persistent "dev" server stack (`docker-compose.dev.yml`, project `profy-dev`), and prod (`docker-compose.prod.yml`) — share **one edge Nginx container** (`profi_nginx_prod`) serving both `profy.newlevelhub.kz` and `dev.profy.newlevelhub.kz` from a single `nginx.prod.conf`, deployed by two separate CD pipelines that flock-guard against each other. Container names must stay unique across environments on this shared network (e.g. `db`/`redis` for prod vs. `profi_db_dev`/`profi_redis_dev` for dev — see the "NEVER reuse prod names" comment in `docker-compose.dev.yml`). Any Nginx `location` proxying to a container **must** use lazy per-request resolution (`set $x_upstream http://container:port; proxy_pass $x_upstream;`), never a static `upstream {}` block — see `docs/nginx-prod-points-to-dev-incident.md` for the outage this caused (a missing container in a static upstream crash-loops the whole shared edge Nginx, taking down both domains, not just one).

### Migrations

There are 60+ files in `alembic/versions/` with multiple parallel heads (this repo does not maintain a single linear history). Run `alembic heads` to find the real current head before writing a new migration's `down_revision` — don't infer it by reading filenames.

### Tests

`tests/conftest.py`'s `db_session` fixture wraps each test in an outer transaction + SAVEPOINT (`join_transaction_mode="create_savepoint"`), so code under test calling `session.commit()` only releases the savepoint — nothing persists past the test, and no manual cleanup is needed. `pytest-asyncio` opens a fresh event loop per test, but the app's DB engine pool and several services' lazily-constructed module-level Redis singletons stay bound to the loop that first created them — the `_dispose_engine_pool_per_loop` autouse fixture disposes the engine and closes/resets every such Redis singleton after each test. If you add a new module with its own module-level `redis.asyncio.Redis` singleton, add it to `_REDIS_SINGLETON_MODULES` in `conftest.py` or it will intermittently break with "Event loop is closed" in later tests, not the one that introduced it.
