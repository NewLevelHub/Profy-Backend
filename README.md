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
├── docker-compose.yml
├── Dockerfile
├── nginx.conf
├── requirements.txt
└── .env.example
```

## Быстрый старт

```bash
cp .env.example .env

# SSL-сертификаты для nginx :443 (один раз)
mkdir -p nginx/ssl && openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/ssl/key.pem -out nginx/ssl/cert.pem -subj "/CN=localhost"

docker compose up -d --build
```

Первый билд может занять несколько минут — pip скачивает зависимости внутри Docker.

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
