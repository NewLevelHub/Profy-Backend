# Profi Backend

Backend API платформы профориентации Profi.

## Стек

- **FastAPI** — HTTP API (SQLAlchemy 2.0 async)
- **PostgreSQL 16** — основная БД
- **Redis 7** — кэш, rate limiting
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

## Сервисы (локально)

| Сервис | Образ | Назначение |
|--------|-------|------------|
| `api` | `python:3.11-slim` | FastAPI + Uvicorn |
| `db` | `postgres:16-alpine` | PostgreSQL |
| `redis` | `redis:7-alpine` | Redis |
| `nginx` | `nginx:alpine` | Reverse proxy |

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

Основные группы эндпоинтов (все под `/api/v1`): `auth`, `admin`, `profile` (+ `profile/artifacts`), `assessment` (+ questions/question-pairs/motivation/motivation-pairs), `directions`, `inquiry`, `result`, `roadmap`, `universities`. Полный список — в Swagger UI.

## Переменные окружения

`.env` (шаблон — `.env.example`). Ключевые:

| Переменная | Описание |
|---|---|
| `DATABASE_URL` | PostgreSQL (`postgresql+asyncpg://…`) |
| `REDIS_URL` | Redis URL |
| `SECRET_KEY` | Секрет для JWT (сменить в production) |
| `LLM_API_KEY` | Ключ LLM-провайдера (опционально) |
| `LLM_ENABLED` | Включает генерацию roadmap через LLM; `false` по умолчанию — тогда используются статические шаблоны |
| `LLM_MODEL`, `LLM_BASE_URL`, `LLM_TIMEOUT`, `LLM_MAX_TOKENS`, `LLM_TEMPERATURE` | Настройки обычных (лёгких) LLM-вызовов |
| `LLM_ROADMAP_TIMEOUT`, `LLM_ROADMAP_MAX_TOKENS`, `LLM_ROADMAP_MODEL` | Отдельные, более щедрые настройки для генерации roadmap — она заметно крупнее остальных LLM-вызовов |
| `RESEND_API_KEY` | Ключ [Resend](https://resend.com) для отправки email (коды подтверждения, сброс пароля). Пусто — коды просто логируются в консоль, письма не отправляются |
| `EMAIL_FROM` | Адрес отправителя писем |
| `GOOGLE_CLIENT_ID` | Client ID из Google Cloud Console для входа через Google (веб) |
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

## Миграции

В `alembic/versions/` больше 60 файлов, и история миграций **не линейна** — есть несколько параллельных head'ов. Перед созданием новой миграции проверьте актуальный head:

```bash
docker compose exec api alembic heads
```

## Seed-данные

Вопросы (RIASEC / Big Five / MI), forced-choice пары, мотивационные утверждения/пары и RIASEC-направления описаны в Python-файлах-«банках» (`scripts/*_bank.py`) — это источник правды, а не БД напрямую. Соответствующий `scripts/seed_*.py` при каждом запуске **полностью синхронизирует** БД с банком: обновляет изменившиеся поля, добавляет новые строки и **удаляет** те, ключа которых больше нет в банке. Чтобы поменять контент — редактируйте файл-банк и перезапускайте seed-скрипт, а не правьте строки в БД напрямую (правки не переживут следующий деплой/reseed).

Полный и актуальный порядок всех seed/backfill/apply-скриптов, которые гоняются на каждый деплой, — в `.github/workflows/cd.yml` / `cd-dev.yml`.

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

Push в `dev` или `main` триггерит `.github/workflows/cd-dev.yml` / `cd.yml`: сборка образа → деплой на соответствующий сервер → миграции → полный прогон seed/backfill-скриптов. `dev.profy.newlevelhub.kz` и `profy.newlevelhub.kz` обслуживаются одним общим edge-nginx контейнером на проде — при правках `nginx.prod.conf` см. `docs/nginx-prod-points-to-dev-incident.md`. Фото на сервер кладутся один раз вручную (`/srv/profy-media`, монтируется в контейнеры как `/srv/media`) — CI их не трогает.

## Дополнительная документация

- `CLAUDE.md` — архитектурные заметки и нюансы для работы с кодом (контент-пайплайн, топология деплоя, тестовая инфраструктура и т.д.)
- `docs/` — контракты API, планы фич, разборы инцидентов
