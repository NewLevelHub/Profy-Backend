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

`start.sh`, `.env`, `.env.local`, `docker-compose.local.yml`, `nginx.local.conf` лежат в `.gitignore` — возьми их у команды и положи в корень репозитория. Шаблоны переменных — [`.env.example`](.env.example) и [`.env.local.example`](.env.local.example) (`cp .env.local.example .env.local`; `docker-compose.local.yml` читает оба файла).

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

Основные группы эндпоинтов (все под `/api/v1`): `auth`, `admin`, `profile` (+ `profile/artifacts`), `assessment` (+ questions/question-pairs/motivation), `result`, `universities`, `psychologist`. Полный список — в Swagger UI.

## Переменные окружения

`.env` (шаблон — `.env.example`). Ключевые:

| Переменная | Описание |
|---|---|
| `DATABASE_URL` | PostgreSQL (`postgresql+asyncpg://…`) |
| `REDIS_URL` | Redis URL |
| `SECRET_KEY` | Секрет для JWT (сменить в production) |
| `LLM_API_KEY` | Ключ LLM-провайдера (опционально) |
| `LLM_ENABLED` | Включает LLM-нарратив отчёта и AI-анализ для психолога; `false` по умолчанию — тогда нарратив собирается из шаблонов |
| `LLM_MODEL`, `LLM_BASE_URL`, `LLM_TIMEOUT`, `LLM_MAX_TOKENS`, `LLM_TEMPERATURE` | Настройки обычных (лёгких) LLM-вызовов |
| `RESEND_API_KEY` | Ключ [Resend](https://resend.com) для отправки email (коды подтверждения, сброс пароля). Пусто — письма не отправляются |
| `API_DOCS_ENABLED` | Отдавать Swagger UI (`/docs`) и `/openapi.json`. По умолчанию `true`; в `docker-compose.prod.yml` зафиксировано `false` — см. [Заголовки безопасности и документация API](#заголовки-безопасности-и-документация-api) |
| `LOG_EMAIL_CODES` | Только локально: при пустом `RESEND_API_KEY` писать коды в лог `api` (`true` в `.env.example`). По умолчанию `false`, на сервере не включать |
| `EMAIL_FROM` | Адрес отправителя писем |
| `GOOGLE_CLIENT_ID` | Client ID из Google Cloud Console для входа через Google (веб) |
| `CORS_ALLOWED_ORIGINS` | Сайты, страницам которых браузер разрешит читать ответы API, через запятую. Локально `http://localhost:5173`; на серверах задаётся в compose-файлах — см. [CORS](#cors-какие-сайты-могут-обращаться-к-api) |
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

История миграций линейная — **одна голова**, и это проверяется автоматически (PRO-429).

**Один раз на клон** включите git-хуки (`start.sh` делает это сам):

```bash
git config core.hooksPath .githooks
```

Дальше всё само:

- создаёте миграцию только через `docker compose exec api alembic revision --autogenerate -m "..."` — id руками не придумываем;
- если коллега успел влить свою миграцию в `dev`, то после `git pull origin dev` хук сам перевесит вашу миграцию поверх его и закоммитит это;
- на `git push` хук проверит то же самое. Если он что-то исправил — закоммитит и попросит повторить `git push`. Если в `dev` есть миграции, которых нет у вас, — попросит сначала `git pull origin dev`;
- вручную то же самое: `python scripts/migrations_fix.py fix` (только git и файлы, БД не нужна).

Правила:

- **Не правьте, не удаляйте и не перевешивайте миграции, которые уже есть в `dev`/`main`** — они применены на dev-сервере/проде. Исправление — только новой миграцией.
- **Не создавайте merge-миграции** (`alembic merge heads`) — вместо них `migrations_fix.py fix`.

На каждый PR в `dev`/`main` CI (`migrations-guard.yml`) проверяет: одна голова, влитые миграции не тронуты, `alembic upgrade head` проходит на чистой БД, модели совпадают с миграциями (старые известные расхождения — в `alembic/known_schema_drift.txt`, новые туда не добавляем). Осознанная правка влитой миграции — только с меткой `migration-edit-approved` на PR.

## Seed-данные

Вопросы (RIASEC / Big Five / психологические тесты), forced-choice пары (ДДО), мотивационные утверждения и RIASEC-направления описаны в Python-файлах-«банках» (`scripts/*_bank.py`) — это источник правды, а не БД напрямую. Соответствующий `scripts/seed_*.py` при каждом запуске **полностью синхронизирует** БД с банком: обновляет изменившиеся поля, добавляет новые строки и **удаляет** те, ключа которых больше нет в банке. Чтобы поменять контент — редактируйте файл-банк и перезапускайте seed-скрипт, а не правьте строки в БД напрямую (правки не переживут следующий деплой/reseed).

Полный и актуальный порядок всех seed/apply-скриптов (и `build_universities.py`), которые гоняются на каждый деплой, — в `.github/workflows/cd.yml` / `cd-dev.yml`.

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

Push в `dev` или `main` запускает `.github/workflows/cd-dev.yml` / `cd.yml`: сборку образа, деплой своего окружения, миграции и seed-скрипты. Общий edge-nginx обслуживает `dev.profile.newlevelhub.kz` и `profile.newlevelhub.kz`, но его конфигурацию и сертификаты обновляет только деплой `main`. Dev не пересоздаёт prod-контейнеры и не записывает файлы в prod-путь. Переменные образов разделены: `DEV_API_IMAGE` / `PROD_API_IMAGE`; CD записывает их в соответствующий env-файл автоматически. При ручном запуске Compose нужно задать соответствующую переменную — старый `API_IMAGE` больше не используется. Общие фото `/srv/profy-media` доступны dev только для чтения. Импорт фото и `build_universities.py` выполняются отдельно при необходимости.

### CORS: какие сайты могут обращаться к API

API отдаёт ответы браузерным скриптам только тех сайтов, что перечислены в `CORS_ALLOWED_ORIGINS`. Запросы с любого другого сайта браузер блокирует. Мобильных приложений, `curl` и запросов сервер-сервер это не касается.

Значения по умолчанию лежат в compose-файлах и приезжают на сервер вместе с деплоем, **на сервере ничего настраивать не нужно**:

| Окружение | Файл | Разрешённый сайт |
|---|---|---|
| prod | `docker-compose.prod.yml` | `https://profile.newlevelhub.kz` |
| dev | `docker-compose.dev.yml` | `https://dev.profile.newlevelhub.kz` |

**Когда это нужно менять.** Только если фронтенд (или другой веб-клиент) начинает открываться с нового адреса: сменился домен, добавился второй домен, фронтенд вынесли на отдельный хост. Признак проблемы — в консоли браузера ошибка `blocked by CORS policy`, а в ответе API на `OPTIONS` — `400 Disallowed CORS origin`.

**Как менять.**

1. Постоянно — поправить домен в строке `CORS_ALLOWED_ORIGINS` нужного compose-файла и выкатить как обычно.
2. Без правки кода — добавить строку в `.env.production` / `.env.development` на сервере и пересоздать контейнер API (следующий деплой сделает это сам). Строка **заменяет** значение по умолчанию, поэтому текущий домен в ней тоже нужно указать:

   ```
   CORS_ALLOWED_ORIGINS=https://profile.newlevelhub.kz,https://new.example.kz
   ```

**Формат.** Адреса через запятую, каждый — ровно `схема://хост[:порт]`: без пути и без `*`. На неверном значении (в том числе `*` или `https://*.example.kz`) API не запустится, в логах контейнера будет `CORS_ALLOWED_ORIGINS: ... is not an exact origin`. Так сделано намеренно: `*` позволил бы любому сайту читать ответы API.

**Как проверить после изменения** (подставить нужный домен):

```bash
curl -s -o /dev/null -D - -X OPTIONS https://profile.newlevelhub.kz/api/v1/auth/login \
  -H "Origin: https://profile.newlevelhub.kz" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization,content-type"
```

Для разрешённого сайта ответ `200` с заголовком `access-control-allow-origin: <этот сайт>`; для чужого — `400` без этого заголовка.

Разрешённые методы и заголовки запросов (`Authorization`, `Content-Type`, `Accept-Language`) заданы в `app/main.py`. Если клиент с другого домена начнёт слать новый заголовок, его нужно добавить туда.

### Заголовки безопасности и документация API

Всё настроено в файлах репозиториев и приезжает с деплоем; на сервере руками
ничего делать не нужно. Раздел — на случай, если что-то из этого придётся
менять или разбирать поломку.

**Документация API закрыта на проде.** `https://profile.newlevelhub.kz/docs`
и `/openapi.json` не отдаются: схема перечисляет все адреса API, включая
админские. Закрыто в двух местах — в `nginx.prod.conf` у прод-хоста нет этих
`location`, и в `docker-compose.prod.yml` стоит `API_DOCS_ENABLED: "false"`.
На dev-стенде (`dev.profile.newlevelhub.kz/docs`) и локально Swagger работает
как раньше.

**Заголовки общего nginx** (`nginx.prod.conf`, оба HTTPS-хоста):

| Заголовок | Значение | Зачем |
|---|---|---|
| `Strict-Transport-Security` | `max-age=31536000` | браузер год ходит на сайт только по HTTPS |
| `X-Content-Type-Options` | `nosniff` | браузер не угадывает тип файла |
| `X-Frame-Options` | `DENY` | сайт нельзя встроить в чужую страницу |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | наружу уходит только домен, без пути |

Плюс `server_tokens off` — nginx не сообщает свою версию.

Что важно знать при правках:

- **HSTS не отменить быстро.** Браузер, получивший заголовок, год не пойдёт на
  сайт по HTTP. Если сертификат истечёт, сайт у таких пользователей не
  откроется вообще, без кнопки «всё равно перейти». Продление сертификатов
  должно работать. `includeSubDomains` намеренно не указан: правило действует
  только на сам хост, а не на поддомены, которые никто не проверял.
- **`add_header` в `location` отменяет заголовки хоста.** Если в каком-то
  `location` появляется свой `add_header`, nginx перестаёт добавлять туда
  заголовки из блока `server`. Поэтому в `/media/` они повторены. Добавляете
  `add_header` в новый `location` — повторите там все четыре; это проверяет
  `tests/deployment`.

**Размер запроса.** `client_max_body_size 2M` во всех nginx-конфигах, включая
локальные. API принимает только JSON, загрузки файлов нет; самый большой
законный запрос — документ банка АСТУР, около 110 КБ. Запрос крупнее 2 МБ
nginx отклоняет с `413`, не передавая в API. Если появится загрузка файлов,
лимит нужно поднять только для её `location`, а не для всего хоста. Размеры
отдельных полей ограничены в схемах запросов (`app/schemas/`), общие
константы — в `app/schemas/validation.py`.

**Content-Security-Policy** задаётся не здесь, а в репозитории фронтенда
(`Profy-Frontend/nginx/nginx.conf`), потому что зависит от того, что грузит
страница. Если после деплоя фронта что-то перестало грузиться (шрифты, вход
через Google, картинки), в консоли браузера будет строка
`Refused to … because it violates the following Content Security Policy
directive` — по ней видно, какой источник нужно добавить в политику.

**Как проверить после деплоя:**

```bash
curl -sI https://profile.newlevelhub.kz/ | grep -iE 'strict-transport|content-security|x-content-type|x-frame|referrer-policy|^server'
curl -s -o /dev/null -w '%{http_code}\n' https://profile.newlevelhub.kz/openapi.json   # не JSON схемы: отвечает страница сайта
```

## Дополнительная документация

- `CLAUDE.md` — архитектурные заметки и нюансы для работы с кодом (контент-пайплайн, топология деплоя, тестовая инфраструктура и т.д.)
- `docs/` — контракты API, планы фич, разборы инцидентов
