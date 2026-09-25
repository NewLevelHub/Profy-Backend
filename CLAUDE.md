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
# ... other scripts/seed_*.py, apply_direction_content.py, build_universities.py — see
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

RIASEC/Big Five and psych-test questions, forced-choice question pairs (ДДО), motivation statements, and RIASEC directions are defined in static Python "bank" files (`scripts/riasec_question_bank.py`, `scripts/bigfive_question_bank.py`, `scripts/motivation_statement_bank.py`, `scripts/professional_types_bank.py`, etc.), not edited directly in the DB. The corresponding `scripts/seed_*.py` script is a **self-healing full resync**, run on every CD deploy: it diffs and overwrites the DB row's fields to match the bank, inserts missing rows, and **deletes any DB row whose key is no longer in the bank**. To change this content, edit the bank file and re-run its seed script — do not hand-edit these rows in the DB, a redeploy will revert or delete them. (`University`/`Program` rows are different: they come from one committed file, `scripts/data/university_snapshot.clean.json` (built by `scripts/build_catalog.py`), loaded by `scripts/build_universities.py`, which prunes rows not in the snapshot and upserts the rest with deterministic ids, skipping admin-locked fields — see its module docstring.)

The CD pipeline (`.github/workflows/cd.yml`, `cd-dev.yml`) runs 7 of these scripts sequentially after every deploy, in a fixed order (question-bank seeds, `apply_direction_content.py`, `build_universities.py`, `rename_university_photos.py`) — most are idempotent no-ops once their target state is reached, but some overwrite-if-different rather than fill-if-empty, so re-ordering them or assuming any one is side-effect-free needs checking the individual script.

**Localization (`ru`/`kk`):** bank-seeded content tables (`questions`, `question_pairs`, `motivation_statements`, `directions`) are one row per logical item (one row per question/pair/statement/direction — never one row per locale; that "variant A" row-per-locale design was replaced 2026-09-14, see `docs/i18n-contract.md`'s decision log). Localizable fields are JSONB `{"ru": ..., "kk": ...}` maps read via `app/i18n.py::pick_locale()` (or `pick_locale_list()` for the list-valued `Direction` fields); non-localizable structural fields (`order`, `riasec_type`, `holland_code`, `category`, …) are plain scalar columns, physically shared — there is no second copy of them that could drift out of sync. Bank entries hold `text` as `{"ru": ..., "kk": ...}` already, so the seed full-resync writes the whole map in one upsert per natural key and deletes any DB row whose key is no longer in the bank. Kazakh translations are edited in the bank files, never in the DB. Request locale resolves as `users.locale` → `Accept-Language` → `ru`; read through `app/i18n.py::get_locale()` / `pick_locale()`. `kk` is live since KZ-603 (`SUPPORTED_LOCALES = ("ru", "kk")`) — there is no feature flag, so rollback is a `revert` of that one change.

Localized text lives in **three** shapes, and which one applies depends on where the text sits — do not add a fourth without reading the contract:
1. **A `{"ru": ..., "kk": ...}` JSONB map, the field's only storage** (above) — one row per item, bank-seeded content edited in `scripts/*_bank.py`; read via `pick_locale()`/`pick_locale_list()`.
2. **A `*_i18n` JSONB overlay next to a separate plain `ru` column** (`University.description`, `Program.name`, …) — free text that predates translation and owns a column, so `ru` stays a plain scalar and only non-`ru` overrides live in the sibling map; read via `app/i18n.resolve_column_i18n`, authored in `scripts/data/catalog_descriptions_kk.json`.
3. **A dictionary keyed by the source string** (`app/i18n/data/program_requirements_kk.json`) — free text buried *inside* a JSONB blob (`Program.requirements`'s `notes`/`exams`/documents, `Program.language`, grant names/conditions). Keyed by the phrase rather than the row because ~12.4k programs share only ~4.6k distinct phrases; read via `app/i18n/data_strings.py`, authored with `scripts/apply_requirements_kk.py`. No migration and no seed step — the committed file *is* the store.

Kazakh translations are edited in these files, never in the DB. Full contract: `docs/i18n-contract.md`.

#### Review/data files must reference rows by a portable key, never a bare row UUID

Any review/data file under `scripts/data/**` (or `scripts/*review*.json`) that points at a `University`/`Program` row MUST carry a cross-DB-portable key — `slug` / `university_slug` (curated rows), `jinaq_external_id` (jinaq rows, resolved via `university_external_refs`), or `ror_id`; a `Program` also needs its *name* to resolve under that University. A bare `University.id` / `Program.id` is a per-database random `uuid4()` and resolves to nothing on any other DB (a fresh local copy, prod's first import run) — the apply script then silently no-ops on every entry. Resolve rows through `scripts/entity_resolver.py` (`resolve_university` / `resolve_program`), not a hand-rolled `where(University.id == ...)`. Enforced by `tests/unit/test_review_files_portable_keys.py`.

#### Exception: АСТУР content lives in versioned DB rows, not a Python bank

АСТУР (`app/services/astur/`, PRO-427) is not bank-file content. Its questions, options, answer keys, synonym tiers, scoring methods and timers are one document per **immutable published version** in `astur_bank_versions` (`draft → validate → publish`, admin API under `/api/v1/admin/astur/bank-versions`). Version 1 is `app/data/astur_bank_v1.json`, inserted by migration `a7c3e1f9b2d4`; its hash is pinned by `tests/unit/test_astur_bank.py` — never edit that file, publish a new version instead. Every attempt (`astur_runs.bank_version_id`) is pinned to the version it was started on and is scored once, at finalize, into a frozen `result_snapshot`; reports read the snapshot and never rescore. Scoring thresholds are versioned in `app/data/astur_scoring_rules.json` (add a version, don't edit one). `scripts/backfill_astur_legacy_snapshots.py` (idempotent, run on deploy) freezes attempts finished before snapshots existed.

### Assessment: one battery, multiple instruments

The audience is 14-18 and everyone takes the same battery — there are no age tiers (removed in PRO-425; `Profile.age_group` survives only for the goal logic). Every `Question` row (`app/models/question.py`) carries an `instrument` (`riasec`, `big_five`, the psych tests, …) in one shared table, and every row is shown to everyone. Motivation is MOST/LEAST triplets (`motivation_service`). Forced-choice `QuestionPair` rows (today only the ДДО pairs, instrument `professional_types`) and Likert `Question` rows are scored through the same `UserResponse` path — a picked pair choice is written as two synthetic Likert-equivalent responses (see `app/services/question_pair_service.py`), so scoring services don't need to know pairs exist.

### Agent localization rule

Every user-facing API detail, validation error, notification, and response text must use the localization catalog. Never add Russian, Kazakh, or English UI copy as a literal in a router, service, schema, or handler. Add matching `ru` and `kk` keys under `app/i18n/catalog/`, preserve interpolation placeholders, and resolve text through the active request locale. Technical logs, identifiers, SQL, paths, and protocol values are excluded.

### LLM: report narrative and psychologist AI analysis

`app/services/llm_client.py::is_enabled()` gates all LLM calls on `LLM_ENABLED and LLM_API_KEY` — off by default. The report narrative (`report_narrative_service`) falls back to deterministic templates when disabled; the psychologist's AI analysis (`psych_ai_analysis_service`) is simply absent. There is no roadmap — it was removed in PRO-425.

### Admin endpoints

`app/routers/admin.py` exposes read + PATCH editing for `University`/`Program` (no create/delete) via `admin_university_service`, with `admin_locked_fields` so CD reseeds don't overwrite admin edits. Question-bank content (questions / pairs / motivation / directions) is editable too: admin edits live in an `overrides` JSONB layer composed on top of the seed banks at sync time (`admin_content_service` + `admin_lock`). Frontend contracts: `docs/frontend-admin-university-api-contract.md`, `docs/frontend-admin-questions-api-contract.md`, `docs/frontend-admin-users-api-contract.md`.

### Deploy topology (relevant when touching docker-compose/nginx)

Three separate environments — local (`docker-compose.yml`), a persistent "dev" server stack (`docker-compose.dev.yml`, project `profy-dev`), and prod (`docker-compose.prod.yml`) — share **one edge Nginx container** (`profi_nginx_prod`) serving both `profy.newlevelhub.kz` and `dev.profy.newlevelhub.kz` from a single `nginx.prod.conf`, deployed by two separate CD pipelines that flock-guard against each other. Container names must stay unique across environments on this shared network (e.g. `db`/`redis` for prod vs. `profi_db_dev`/`profi_redis_dev` for dev — see the "NEVER reuse prod names" comment in `docker-compose.dev.yml`). Any Nginx `location` proxying to a container **must** use lazy per-request resolution (`set $x_upstream http://container:port; proxy_pass $x_upstream;`), never a static `upstream {}` block — see `docs/nginx-prod-points-to-dev-incident.md` for the outage this caused (a missing container in a static upstream crash-loops the whole shared edge Nginx, taking down both domains, not just one).

### Migrations

There are 60+ files in `alembic/versions/` with multiple parallel heads (this repo does not maintain a single linear history). Run `alembic heads` to find the real current head before writing a new migration's `down_revision` — don't infer it by reading filenames.

### Tests

`tests/conftest.py`'s `db_session` fixture wraps each test in an outer transaction + SAVEPOINT (`join_transaction_mode="create_savepoint"`), so code under test calling `session.commit()` only releases the savepoint — nothing persists past the test, and no manual cleanup is needed. `pytest-asyncio` opens a fresh event loop per test, but the app's DB engine pool and several services' lazily-constructed module-level Redis singletons stay bound to the loop that first created them — the `_dispose_engine_pool_per_loop` autouse fixture disposes the engine and closes/resets every such Redis singleton after each test. If you add a new module with its own module-level `redis.asyncio.Redis` singleton, add it to `_REDIS_SINGLETON_MODULES` in `conftest.py` or it will intermittently break with "Event loop is closed" in later tests, not the one that introduced it.
