# Profi Backend

Backend API для мобильного приложения Profi.

## Стек

- **FastAPI** — HTTP API
- **PostgreSQL 16** — основная БД (SQLAlchemy 2.0 async)
- **Redis 7** — кэш и очереди
- **Alembic** — миграции
- **Nginx** — reverse proxy (80/443 → api:8000)
- **Docker Compose** — локальная разработка

## Структура проекта

```
Profy-Backend/
├── app/
│   ├── main.py          # FastAPI, CORS, проверка подключения к БД
│   ├── config.py        # Настройки из env (pydantic-settings)
│   ├── database.py      # Async engine и sessionmaker
│   ├── routers/         # HTTP-роутеры
│   ├── models/          # SQLAlchemy-модели
│   ├── schemas/         # Pydantic-схемы
│   ├── services/        # Бизнес-логика
│   └── prompts/         # LLM-промпты
├── alembic/             # Миграции (async SQLAlchemy)
├── scripts/
│   └── seed_questions.py  # Наполнение БД вопросами
├── docker-compose.yml
├── Dockerfile
├── nginx/
│   └── local.conf       # локальный reverse proxy (production: nginx.conf на сервере)
├── requirements.txt
└── .env.example
```

## Быстрый старт

```bash
cp .env.example .env

docker compose up -d --build
```

Локальный nginx проксирует API на `http://localhost/docs` и фронтенд с `localhost:3000` (если запущен `Profy-Frontend`).

## Сервисы

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

API пока без эндпоинтов — роутеры подключаются в `app/routers/`.

## Переменные окружения

Скопируйте `.env.example` в `.env` и при необходимости измените значения:

| Переменная | Описание |
|------------|----------|
| `DATABASE_URL` | PostgreSQL connection string (`postgresql+asyncpg://...`) |
| `REDIS_URL` | Redis URL |
| `SECRET_KEY` | Секрет для JWT (сменить в production) |
| `LLM_API_KEY` | Ключ LLM-провайдера (опционально) |

## Seed-данные (вопросы для тестирования)

После применения миграций нужно наполнить БД вопросами:

```bash
docker compose exec api python scripts/seed_questions.py
```

Скрипт добавит **213 вопросов**, покрывающих все 9 блоков опросника (`interests`, `thinking`, `personality`, `motivation`, `academic`, `directions`, `goal_clarification`, `university`, `wellbeing`) и три возрастные группы (`junior`, `middle`, `senior`). Блок `university` — только для `senior`.

Скрипт **идемпотентен**: upsert по ключу (блок, возрастная группа, порядковый номер) — повторный запуск не создаёт дубликаты; изменённые текст/варианты обновляются, неизменённые вопросы пропускаются.

```
Done. Inserted: 213, updated: 0, skipped (unchanged): 0
# При повторном запуске:
Done. Inserted: 0, updated: 0, skipped (unchanged): 213
```

Структура вопроса в БД:

```json
{
  "text": "Что тебе больше всего нравится на уроках?",
  "options": [
    { "text": "Считать и решать задачки", "weights": { "science": 2, "technology": 1 } },
    { "text": "Рисовать и мастерить",     "weights": { "art": 2, "creative": 2 } }
  ]
}
```

Поле `weights` используется алгоритмом рекомендаций и **не возвращается** на фронтенд через API.

## Полезные команды

```bash
# Статус контейнеров
docker compose ps

# Логи API
docker compose logs -f api

# Остановить
docker compose down

# Остановить и удалить volumes (сброс БД)
docker compose down -v

# Миграции (внутри контейнера api)
docker compose exec api alembic upgrade head

# Наполнение вопросами (после миграций)
docker compose exec api python scripts/seed_questions.py
```

## Проверка

После `docker compose up -d`:

1. Все 4 сервиса в статусе `running` / `healthy`
2. `GET http://localhost/docs` → Swagger UI (HTTP 200)
3. В логах api: `Database connected`

```bash
docker compose logs api | grep "Database connected"
curl -s -o /dev/null -w "%{http_code}\n" http://localhost/docs
```
