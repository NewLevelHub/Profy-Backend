You are an expert in FastAPI and Python backend development.

## Key Principles
- Write concise, technical responses with accurate Python examples
- Favor functional, declarative programming over class-based approaches
- Prioritize modularization to eliminate code duplication
- Use descriptive variable names with auxiliary verbs (e.g., `is_active`, `has_permission`)
- Employ lowercase with underscores for file/directory naming (e.g., `routers/user_routes.py`)
- Export routes and utilities explicitly
- Follow the RORO (Receive an Object, Return an Object) pattern

## Python/FastAPI Standards
- Use `def` for pure functions, `async def` for asynchronous operations
- Use type hints for all function signatures; prefer Pydantic models over raw dictionaries
- Structure modules: exported router → sub-routes → utilities → static content → types (models, schemas)
- Omit curly braces for single-line conditionals; write concise one-line conditional syntax

## Error Handling
- Handle edge cases at function entry points
- Employ early returns for error conditions; place happy path logic last
- Avoid unnecessary `else` statements; use if-return patterns
- Implement guard clauses for preconditions
- Use `HTTPException` for expected errors and model them as specific HTTP responses
- Provide proper error logging and user-friendly messaging

## FastAPI-Specific Guidelines
- Use plain functions and Pydantic models for input validation
- Declare routes with clear return type annotations
- Prefer lifespan context managers for managing startup/shutdown events
- Leverage middleware for logging, error monitoring, and optimization
- Apply Pydantic's `BaseModel` consistently for validation

## Performance Optimization
- Minimize blocking I/O; use `async` for all database and API calls
- Implement caching with Redis or in-memory stores
- Optimize Pydantic serialization/deserialization
- Use lazy loading for large datasets

## Project File Structure (Best Practice)

```
project/
├── app/
│   ├── main.py                  # App factory, lifespan, middleware registration
│   ├── config.py                # Settings via pydantic-settings (BaseSettings)
│   ├── dependencies.py          # Shared FastAPI dependencies (db session, auth, etc.)
│   │
│   ├── routers/                 # One file per domain/resource
│   │   ├── __init__.py
│   │   ├── users.py
│   │   └── items.py
│   │
│   ├── schemas/                 # Pydantic request/response models
│   │   ├── __init__.py
│   │   ├── user.py
│   │   └── item.py
│   │
│   ├── models/                  # SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   ├── user.py
│   │   └── item.py
│   │
│   ├── services/                # Business logic, decoupled from HTTP layer
│   │   ├── __init__.py
│   │   ├── user_service.py
│   │   └── item_service.py
│   │
│   ├── repositories/            # DB access layer (queries, CRUD)
│   │   ├── __init__.py
│   │   ├── user_repo.py
│   │   └── item_repo.py
│   │
│   ├── core/                    # Cross-cutting concerns
│   │   ├── __init__.py
│   │   ├── security.py          # JWT, password hashing
│   │   ├── exceptions.py        # Custom exception classes
│   │   └── logging.py
│   │
│   └── db/
│       ├── __init__.py
│       ├── session.py           # Async engine, sessionmaker
│       └── migrations/          # Alembic migrations
│
├── tests/
│   ├── conftest.py
│   ├── unit/
│   └── integration/
│
├── alembic.ini
├── pyproject.toml
└── .env
```

**Rules:**
- Routers only handle HTTP concerns (request parsing, response building); delegate logic to services
- Services contain business logic and call repositories — never call DB directly from routers
- Repositories contain all SQLAlchemy queries — services never import `Session` directly
- Schemas live in `schemas/`, ORM models in `models/` — never mix them
- Shared dependencies (auth, db session) go in `dependencies.py`, not inside routers
- Config is always loaded through `config.py` (`BaseSettings`), never `os.getenv()` inline

## Dependencies
FastAPI, Pydantic v2, asyncpg/aiomysql, SQLAlchemy 2.0, pydantic-settings, alembic

## Docker Workflow

All commands run inside Docker — never locally. The app code is **baked into the image** (no bind-mount), so after any file change the image must be rebuilt before running commands.

### Common commands

```bash
# Start all services (rebuild api image on code changes)
docker-compose up --build -d

# Apply Alembic migrations
docker-compose exec api alembic upgrade head

# Check current migration revision
docker-compose exec api alembic current

# Run a one-off command without a running container
docker-compose run --rm api <command>

# View api logs
docker-compose logs -f api
```

### Rules
- Never run `alembic`, `python`, or `pip` commands directly on the host machine
- After creating or modifying any file, always rebuild: `docker-compose up --build -d api`
- The DATABASE_URL uses `db` as the host (Docker internal network) — `localhost` only works inside the container
- Exception: `python scripts/migrations_fix.py` runs on the host — it uses only git and files, no DB or app imports

## Alembic Migrations

The history must have exactly **one head** — enforced by git hooks (`.githooks/`, enabled by `./start.sh`) and by CI on every PR (`migrations-history`, `migrations-schema`). Full rules: the "Migrations" section of `CLAUDE.md`.

### Writing a migration

```bash
# 1. Rebuild so the container sees your model changes, bring the DB to head
docker-compose up --build -d api
docker-compose exec api alembic upgrade head

# 2. Generate — the only way to create a migration
docker-compose exec api alembic revision --autogenerate -m "add_x_to_y"

# 3. The file is created inside the container — copy it out to alembic/versions/
docker-compose cp api:/app/alembic/versions/<file>.py alembic/versions/
```

4. Read the generated file before committing: no unexpected `drop_table` / `drop_column` / `drop_index`, enums and server defaults are what you meant, `downgrade()` reverses `upgrade()`.
5. Rebuild and apply it: `docker-compose up --build -d api && docker-compose exec api alembic upgrade head`.
6. Commit the migration together with the model change.

### Rules
- Never hand-type a revision id or copy an old migration file as a template — ids come only from `alembic revision`
- Never edit, delete, rename or re-parent a migration that is already in `dev` or `main` — it is applied on the dev server / prod. Fix forward with a new migration
- Never run `alembic merge heads`. Two heads → `python scripts/migrations_fix.py fix` (the hooks do it automatically on `git pull` / `git push`)
- One migration per change; if you made several while iterating on an unmerged branch, delete them and regenerate one
- Data migrations must not import app models (`app.models.*`) — use `op.execute` / `sa.table()`; models change later, the migration must not
- Never add a line to `alembic/known_schema_drift.txt` to make CI pass — write the migration instead
