# Profi Backend

Backend API платформы профориентации Profi.

## Стек

- **FastAPI** — HTTP API (SQLAlchemy 2.0 async)
- **PostgreSQL 16** — основная БД
- **Redis 7** — кэш
- **Alembic** — миграции
- **Nginx** — reverse proxy (`80 → api:8000`), плюс отдаёт фото вузов прямо из папки
- **Docker Compose** — локальная разработка

## Запуск локально

Проект поднимается одним скриптом — **`./start.sh`**: `docker compose up --build` → ждёт api → `alembic upgrade head` → smoke-проверки → полная последовательность seed-скриптов (вопросы, направления, вузы, программы, рейтинги…).

### 1. Файлы вне гита

`start.sh`, `.env`, `docker-compose.local.yml`, `nginx.local.conf` лежат в `.gitignore` — возьми их у команды и положи в корень репозитория. Шаблон переменных — [`.env.example`](.env.example).

### 2. Фотографии вузов

Фото вузов **не в гите** (~330 МБ). nginx отдаёт их напрямую из папки на диске — объектного хранилища (MinIO/S3) нет.

- Возьми `profy-media.tar.gz` из тим-шары и распакуй **рядом с репозиторием**:
  ```bash
  tar xzf profy-media.tar.gz -C ..
  # → ../profy-media/universities/<slug>.webp   (+ <slug>.card.webp — превью для карточек)
  ```
- Другой путь — переменная `MEDIA_DIR` в окружении, откуда запускаешь `start.sh`.
- **Фото опциональны.** Без папки бэкенд работает, на карточках вузов — иконка-заглушка. Подходит, если задача не про фото.

### 3. Старт

```bash
./start.sh
```

В выводе ищи:

- `Backend is ready: http://localhost/docs`
- `Photo check: GET /media/universities/<slug>.webp -> HTTP 200`
  (или `WARNING: no photos …`, если папку не подкладывал)
- дальше идут seed-скрипты (`Total questions in bank: …` и т.д.)

## Доступ после запуска

| Что | URL |
|---|---|
| Swagger UI | http://localhost/docs |
| OpenAPI JSON | http://localhost/openapi.json |
| Фото вуза | `http://localhost/media/universities/<slug>.webp` |

## Как устроены фото вузов

- Адресуются по `University.slug`: `universities/<slug>.webp`, плюс `<slug>.card.webp` — уменьшенное (~560px) превью для сетки карточек на странице результатов.
- `University.image_url` резолвится **из содержимого папки** (скан `*.webp` один раз на процесс), а не из БД — таблица `university_images` в чтении не участвует. Поэтому папку можно перенести на любой хост с любой БД: фото подхватятся, пока совпадают слаги.
- Пересобрать папку (нужны исходники фото + засеянная БД):
  ```bash
  docker compose exec api python scripts/export_university_photos.py    # <slug>.webp
  docker compose exec api python scripts/generate_card_thumbnails.py    # + <slug>.card.webp
  ```
- Бэкенд хранения — `STORAGE_BACKEND`: `fs` (дефолт, файлы на диске) или `s3` (S3-совместимое). Код — `app/integrations/storage/`.

## Переменные окружения

`.env` (шаблон — `.env.example`). Ключевые:

| Переменная | Описание |
|---|---|
| `DATABASE_URL` | PostgreSQL (`postgresql+asyncpg://…`) |
| `REDIS_URL` | Redis URL |
| `SECRET_KEY` | секрет для JWT |
| `LLM_API_KEY` / `LLM_ENABLED` | LLM-провайдер для roadmap (опционально) |
| `STORAGE_BACKEND` | `fs` (дефолт) или `s3` |
| `STORAGE_FS_ROOT` | путь к фото внутри контейнера (`/srv/media`) |
| `STORAGE_PUBLIC_BASE_URL` | база URL для браузера (локально `http://localhost/media`) |
| `MEDIA_DIR` | путь к папке фото на хосте для `docker compose` (дефолт `../profy-media`) |

## Полезные команды

```bash
docker compose ps                          # статус контейнеров
docker compose logs -f api                 # логи API
docker compose down                        # остановить
docker compose down -v                     # + сбросить БД (удалить volume)
docker compose exec api alembic upgrade head
./start.sh                                  # переподнять и пересидить (идемпотентно)
```

## Структура

```
profi-backend/
├── app/
│   ├── main.py                    # FastAPI, CORS, lifespan
│   ├── config.py                  # настройки (pydantic-settings)
│   ├── routers/                   # HTTP-роутеры
│   ├── models/                    # SQLAlchemy-модели
│   ├── schemas/                   # Pydantic-схемы
│   ├── services/                  # бизнес-логика
│   ├── integrations/storage/      # бэкенды хранения фото (fs / s3) + сборка публичного URL
│   └── prompts/                   # LLM-промпты
├── alembic/versions/              # миграции
├── scripts/                       # seed / apply / import / export — порядок задан в start.sh
├── nginx/local.conf               # локальный reverse proxy (+ /media/ из папки)
├── docker-compose.yml
├── Dockerfile
└── .env.example
```

## Деплой

Прод и дев катятся через GitHub Actions (`.github/workflows/cd.yml` на пуш в `main`, `cd-dev.yml` — в `dev`): собирается образ, на сервер копируются `docker-compose.prod.yml` + `nginx.prod.conf`, затем гоняется тот же список seed-скриптов, что и в `start.sh`. Фото на сервер кладутся один раз вручную (`/srv/profy-media`, монтируется в контейнеры как `/srv/media`) — CI их не трогает.
