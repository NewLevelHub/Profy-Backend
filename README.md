# Profi Backend

Backend API для мобильного приложения Profi.

## Стек

- **FastAPI** — HTTP API
- **PostgreSQL 16** — основная БД (SQLAlchemy 2.0 async)
- **Redis 7** — кэш, rate limiting
- **Alembic** — миграции
- **Nginx** — reverse proxy
- **Docker Compose** — локальная разработка и деплой

## Структура проекта

```
Profy-Backend/
├── app/
│   ├── main.py          # FastAPI, CORS, проверка подключения к БД
│   ├── config.py        # Настройки из env (pydantic-settings)
│   ├── database.py      # Async engine и sessionmaker
│   ├── routers/         # HTTP-роутеры (auth, admin, profile, assessment, roadmap, universities, ...)
│   ├── models/          # SQLAlchemy-модели
│   ├── schemas/         # Pydantic-схемы
│   ├── services/        # Бизнес-логика
│   ├── prompts/         # LLM-промпты (roadmap, direction inquiry, report narrative)
│   ├── templates/       # Email-шаблоны
│   └── data/            # Статические справочники
├── alembic/              # Миграции (async SQLAlchemy)
├── scripts/              # Seed / backfill / apply-скрипты (наполнение и разовые правки данных)
├── tests/
│   ├── unit/             # Без БД
│   └── integration/      # С реальной БД (транзакционный rollback, см. tests/conftest.py)
├── docs/                 # Внутренняя документация: контракты API, планы фич, разборы инцидентов
├── docker-compose.yml         # Локальная разработка
├── docker-compose.dev.yml     # Dev-сервер (staging)
├── docker-compose.prod.yml    # Прод
├── nginx/local.conf           # Локальный reverse proxy
├── nginx.prod.conf            # Edge nginx для dev/prod серверов
├── Dockerfile
├── requirements.txt
└── .env.example
```

## Быстрый старт

```bash
cp .env.example .env

docker compose up -d --build
```

Локальный nginx проксирует API на `http://localhost/docs` и фронтенд с `localhost:3000` (если запущен `Profy-Frontend`).

## Сервисы (локально)

| Сервис | Образ | Назначение |
|--------|-------|------------|
| `api` | `python:3.11-slim` | FastAPI + Uvicorn |
| `db` | `postgres:16-alpine` | PostgreSQL |
| `redis` | `redis:7-alpine` | Redis |
| `nginx` | `nginx:alpine` | Reverse proxy |

## Доступ после запуска

| Сервис | URL |
|--------|-----|
| Swagger UI | http://localhost/docs |
| OpenAPI JSON | http://localhost/openapi.json |

Основные группы эндпоинтов (все под `/api/v1`): `auth`, `admin`, `profile` (+ `profile/artifacts`), `assessment` (+ questions/question-pairs/motivation/motivation-pairs), `directions`, `inquiry`, `result`, `roadmap`, `universities`. Полный список — в Swagger UI.

## Переменные окружения

Скопируйте `.env.example` в `.env` и при необходимости измените значения:

| Переменная | Описание |
|------------|----------|
| `DATABASE_URL` | PostgreSQL connection string (`postgresql+asyncpg://...`) |
| `REDIS_URL` | Redis URL |
| `SECRET_KEY` | Секрет для JWT (сменить в production) |
| `LLM_API_KEY` | Ключ LLM-провайдера (опционально) |
| `LLM_ENABLED` | Включает генерацию roadmap через LLM; `false` по умолчанию — тогда используются статические шаблоны |
| `LLM_MODEL`, `LLM_BASE_URL`, `LLM_TIMEOUT`, `LLM_MAX_TOKENS`, `LLM_TEMPERATURE` | Настройки обычных (лёгких) LLM-вызовов |
| `LLM_ROADMAP_TIMEOUT`, `LLM_ROADMAP_MAX_TOKENS`, `LLM_ROADMAP_MODEL` | Отдельные, более щедрые настройки для генерации roadmap — она заметно крупнее остальных LLM-вызовов |
| `RESEND_API_KEY` | Ключ [Resend](https://resend.com) для отправки email (коды подтверждения, сброс пароля). Пусто — коды просто логируются в консоль, письма не отправляются |
| `EMAIL_FROM` | Адрес отправителя писем |

## Миграции

```bash
docker compose exec api alembic upgrade head
```

В `alembic/versions/` больше 60 файлов, и история миграций **не линейна** — есть несколько параллельных head'ов. Перед созданием новой миграции проверьте актуальный head:

```bash
docker compose exec api alembic heads
```

## Seed-данные

Вопросы (RIASEC / Big Five / MI), forced-choice пары, мотивационные утверждения/пары и RIASEC-направления описаны в Python-файлах-«банках» (`scripts/*_bank.py`) — это источник правды, а не БД напрямую. Соответствующий `scripts/seed_*.py` при каждом запуске **полностью синхронизирует** БД с банком: обновляет изменившиеся поля, добавляет новые строки и **удаляет** те, ключа которых больше нет в банке. Чтобы поменять контент — редактируйте файл-банк и перезапускайте seed-скрипт, а не правьте строки в БД напрямую (правки не переживут следующий деплой/reseed).

```bash
docker compose exec api alembic upgrade head

docker compose exec api python scripts/seed_riasec_questions.py
docker compose exec api python scripts/seed_bigfive_questions.py
docker compose exec api python scripts/seed_mi_questions.py
docker compose exec api python scripts/seed_question_pairs.py
docker compose exec api python scripts/seed_motivation_statements.py
docker compose exec api python scripts/seed_motivation_pairs.py
docker compose exec api python scripts/seed_riasec_directions.py
docker compose exec api python scripts/seed_kz_universities.py
docker compose exec api python scripts/seed_92_professions_universities.py
```

Полный и актуальный порядок всех seed/backfill/apply-скриптов, которые гоняются на каждый деплой, — в `.github/workflows/cd.yml`.

## Тесты

Нужны доступные Postgres и Redis (например, `docker compose up -d db redis`):

```bash
docker compose exec api pytest                                    # всё
docker compose exec api pytest tests/unit                         # без БД
docker compose exec api pytest tests/integration                  # с реальной БД
docker compose exec api pytest tests/unit/test_riasec_service.py::test_name -v   # один тест
```

Каждый тест оборачивается в отдельную транзакцию с rollback в конце (`tests/conftest.py`) — писать вручную очистку данных после теста не нужно.

CI не гоняет тесты автоматически на PR — `cd.yml`/`cd-dev.yml` только деплоят по пушу в `main`/`dev`.

## Деплой

Push в `dev` или `main` триггерит `.github/workflows/cd-dev.yml` / `cd.yml`: сборка образа → деплой на соответствующий сервер → миграции → полный прогон seed/backfill-скриптов. `dev.profy.newlevelhub.kz` и `profy.newlevelhub.kz` обслуживаются одним общим edge-nginx контейнером на проде — при правках `nginx.prod.conf` см. `docs/nginx-prod-points-to-dev-incident.md`.

## Проверка

После `docker compose up -d`:

1. Все 4 сервиса в статусе `running` / `healthy`
2. `GET http://localhost/docs` → Swagger UI (HTTP 200)
3. В логах api: `Database connected`

```bash
docker compose logs api | grep "Database connected"
curl -s -o /dev/null -w "%{http_code}\n" http://localhost/docs
```

## Дополнительная документация

- `CLAUDE.md` — архитектурные заметки и нюансы для работы с кодом (контент-пайплайн, топология деплоя, тестовая инфраструктура и т.д.)
- `docs/` — контракты API, планы фич, разборы инцидентов
