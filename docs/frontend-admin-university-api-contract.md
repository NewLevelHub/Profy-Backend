# Admin University/Program Editing API — контракт для фронтенда

**Статус: реализовано на ветке `pro-227`, актуально на 2026-08-31.**
Основано на прямом чтении `app/routers/admin.py`, `app/dependencies.py`,
`app/services/admin_university_service.py`, `app/schemas/admin_university.py`,
`app/services/admin_lock.py` и `docs/admin-edit-lock-plan.md`.

Фронтенд — отдельный репозиторий (Profy-Frontend), этот документ — контракт
для его команды: что вызывать и как это отрисовывать/сабмитить в админке
списка/поиска/редактирования университетов и программ.

## 1. Доступ

Все эндпоинты ниже требуют `Authorization: Bearer <jwt>` — тот же токен, что
и обычный логин, без отдельного "входа в админку".

- Нет токена / невалидный / просрочен / юзер `is_active=False` → **401**
  `{"detail": "Could not validate credentials"}` (`app/dependencies.py:get_current_user`).
- Токен валиден, но `is_admin=False` → **403**
  `{"detail": "Admin access required"}` (`app/dependencies.py:get_current_admin_user`).

Проверка идёт на каждый запрос заново — снятие `is_admin` у юзера в БД
блокирует его следующий же запрос, даже если токен ещё не истёк.

## 2. Эндпоинты (обзор)

| Method | Path | Назначение |
|---|---|---|
| GET | `/api/v1/admin/universities` | список + поиск |
| GET | `/api/v1/admin/universities/{id}` | детали одного вуза |
| PATCH | `/api/v1/admin/universities/{id}` | редактирование вуза |
| GET | `/api/v1/admin/programs/{id}` | детали одной программы |
| PATCH | `/api/v1/admin/programs/{id}` | редактирование программы |

Создания/удаления вузов и программ через API сейчас нет — см. §10.

## 3. Список + поиск

```text
GET /api/v1/admin/universities?page=1&limit=20&search=narxoz
Authorization: Bearer <token>
```

- `page` — от 1, по умолчанию 1.
- `limit` — 1..100, по умолчанию 20.
- `search` — опционален. **Ищет только по `University.name`**, регистронезависимо,
  частичное совпадение (`ILIKE '%...%'`) — НЕ по городу, стране, `aliases`
  или `short_name`. Не давать в UI понять, что поиск "по всему" — он не такой.
- Сортировка фиксирована — по имени (A→Z), без клиентского контроля сортировки.

```jsonc
{
  "items": [
    {
      "id": "3c122572-96f9-4541-97f7-7d17511d2f18",
      "name": "Narxoz University",
      "city": "Алматы",
      "country": "Казахстан",
      "ranking": 5,               // может быть null
      "uniranks_kz_rank": 3,      // может быть null
      "uniranks_note": null,      // "Н/Р" если проверено и не найдено в рейтинге, иначе null = не проверялось
      "updated_at": "2026-08-30T12:00:00Z", // null, если никогда не редактировался
      "programs_count": 42        // джойн-агрегат, отдельный запрос не нужен
    }
  ],
  "total": 252,
  "page": 1,
  "limit": 20
}
```

`total_pages` бэк не считает — фронт сам: `Math.ceil(total / limit)`.

## 4. Детали университета

```text
GET /api/v1/admin/universities/{university_id}
Authorization: Bearer <token>
```

404 → `{"detail": "University not found"}`.

```jsonc
{
  "id": "3c122572-96f9-4541-97f7-7d17511d2f18",
  "name": "Narxoz University",
  "slug": "universitet-narhoz",       // read-only, не в UpdateRequest — редактировать нельзя
  "short_name": "Нархоз",
  "aliases": ["Народнохозяйственный институт"],
  "location": "г. Алматы, ул. Жандосова 55",
  "country": "Казахстан",
  "city": "Алматы",
  "website": "https://narxoz.edu.kz",
  "ranking": 5,
  "ranking_label": "#5 (Нац. рейтинг)",
  "uniranks_kz_rank": 3,
  "uniranks_world_rank": 1200,
  "uniranks_note": null,
  "description": "...",
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2026-08-30T12:00:00Z",
  "source_url": "https://...",
  "programs": [                        // AdminProgramBrief[] — краткий список программ
    { "id": "...", "name": "Финансы", "language": "Казахский, Русский",
      "cost_per_year": 1800000, "cost_label": null }
  ],
  "admin_locked_fields": ["ranking"]   // см. §7
}
```

## 5. Редактирование университета

```text
PATCH /api/v1/admin/universities/{university_id}
Authorization: Bearer <token>
Content-Type: application/json

{ "ranking": 5, "website": "https://narxoz.edu.kz" }
```

Редактируемые поля (`AdminUniversityUpdateRequest`, все опциональны):

| Поле | Тип |
|---|---|
| `name` | `string` |
| `short_name` | `string` |
| `aliases` | `string[]` |
| `location` | `string` |
| `website` | `string` |
| `ranking` | `int` |
| `ranking_label` | `string` |
| `uniranks_kz_rank` | `int` |
| `uniranks_world_rank` | `int` |
| `uniranks_note` | `string` |
| `description` | `string` |
| `city` | `string` |
| `country` | `string` |
| `source_url` | `string` |

`slug`/`ovpo_code`/`ror_id`/`id`/`created_at`/`programs`/`admin_locked_fields`
не входят в эту схему — если их всё же прислать, pydantic (`extra` не задан →
default `"ignore"`) их просто отбросит, **не 422**, но и эффекта не будет.

Три критичных момента поведения:

1. **Партиальность — по наличию ключа, не по факту изменения значения.**
   Ключ отсутствует в JSON → поле не трогается вообще. Ключ прислан как
   `"ranking": null` → поле явно очищается в `NULL` (это не то же самое, что
   не прислать ключ вовсе). Реализация: `data.model_dump(exclude_unset=True)`
   в `admin_university_service.update_university`.

2. **⚠️ Каждый присланный ключ лочится — независимо от того, изменилось ли
   реально значение.** Это единственное, что может незаметно сломать всю
   фичу: **фронт обязан слать в PATCH только те поля, которые админ реально
   поправил в этом сохранении — никогда не весь стейт формы целиком.**
   Наивная реализация "PATCH весь объект формы при каждом сохранении" после
   первого же сохранения залочит все 14 полей навсегда — ни один будущий
   redeploy'ный seed/backfill-скрипт больше никогда их не тронет, даже если
   это было не нужно. Практика: отслеживать dirty-поля (например,
   `formState.dirtyFields` в `react-hook-form`, либо ручной diff против
   значений, загруженных через GET) и собирать тело PATCH только из них.

3. `aliases` — полная замена массива, не merge/append.

Ответ = обновлённый `AdminUniversityDetail` целиком (со свежим
`admin_locked_fields`).

## 6. Программы

```text
GET /api/v1/admin/programs/{program_id}
PATCH /api/v1/admin/programs/{program_id}
Authorization: Bearer <token>
```

404 (оба метода) → `{"detail": "Program not found"}`.

`AdminProgramDetail` (GET):

```jsonc
{
  "id": "...",
  "university_id": "...",
  "name": "Финансы",
  "language": "Казахский, Русский",
  "cost_per_year": 1800000,       // Decimal -> обычное JSON-число, не строка
  "cost_label": null,
  "description": null,
  "who_its_for": null,
  "requirements": {                // произвольный dict — см. предупреждение ниже
    "notes": ["ЕНТ по математике и физике"],
    "exams": ["Математика", "Физика"],
    "needs_portfolio": false,
    "needs_essay": false
  },
  "deadlines": { "application_close": "2027-07-01" },
  "grants": [],
  "created_at": "...",
  "updated_at": "...",
  "source_url": "...",
  "university": { "id": "...", "name": "Narxoz University" },
  "admin_locked_fields": []
}
```

Редактируемые поля (`AdminProgramUpdateRequest`): `name`, `language`,
`cost_per_year`, `cost_label`, `description`, `who_its_for`, `requirements`
(`dict`), `deadlines` (`dict`), `grants` (`list`), `source_url` — все
опциональны, та же семантика "поле трогается только если ключ прислан" и то
же предупреждение №2 из §5 про полную блокировку поля на любое присланное
значение.

**⚠️ Отдельное, более серьёзное предупреждение для `requirements` /
`deadlines` / `grants`: это замена ВСЕГО объекта/массива целиком, а не
глубокий merge.** `requirements` в БД — это dict, который постепенно
дозаполняется несколькими бэкенд-скриптами разными ключами (`exams`,
`needs_portfolio`, `needs_essay`, `needs_recommendations`, `needs_interview`,
`notes`, иногда `admission_scores_2026` и другие). **Если форма редактирования
показывает не все ключи этого dict'а, фронт обязан взять полный объект,
полученный через GET, поменять в нём только то поле, которое реально
редактировал админ, и отправить в PATCH весь получившийся dict целиком** —
иначе все "невидимые" в форме ключи молча стираются.

Пример правильного поведения — форма меняет только `needs_portfolio`:

```jsonc
// Получено через GET:
// "requirements": {"notes": [...], "exams": [...], "needs_portfolio": false}

// PATCH body — needs_portfolio изменён, но notes/exams сохранены как были:
{
  "requirements": {
    "notes": ["ЕНТ по математике и физике"],
    "exams": ["Математика", "Физика"],
    "needs_portfolio": true
  }
}
```

Отправка `{"requirements": {"needs_portfolio": true}}` (только изменённым
ключом) **сотрёт** `notes` и `exams` этой программы.

## 7. `admin_locked_fields` — что это и как показывать

- Заполняется бэкендом автоматически на каждый PATCH (§5/§6) — клиент не
  может выставить его напрямую (поля нет в обеих `*UpdateRequest`-схемах; если
  прислать — молча проигнорируется, не 422).
- Смысл: защищает конкретное поле от того, что следующий плановый redeploy
  (там прогоняется ~25 seed/backfill-скриптов) тихо перезапишет ручную правку
  админа. **Это НЕ ограничивает дальнейшее редактирование через этот же API**
  — админ может PATCH'ить залоченное поле сколько угодно раз ещё, оно просто
  остаётся залоченным.
- UI: значок замочка/тултип рядом с полем, если оно есть в
  `admin_locked_fields`, текст в духе "Защищено от автоматического обновления
  при следующем деплое".
- Снять лок с поля через API нельзя — см. §10.

## 8. Ошибки

| Код | Когда | Тело |
|---|---|---|
| 401 | нет/невалиден/просрочен токен, юзер неактивен | `{"detail": "Could not validate credentials"}` |
| 403 | токен валиден, но `is_admin=False` | `{"detail": "Admin access required"}` |
| 404 | вуз/программа с данным id не найдены (GET и PATCH) | `{"detail": "University not found"}` / `{"detail": "Program not found"}` |
| 422 | тело PATCH не проходит валидацию pydantic (например, строка вместо `int` в `ranking`) | стандартный FastAPI validation-error shape |

## 9. Что нужно построить на фронте

1. **Страница списка университетов** — инпут поиска с debounce (~300-400мс) →
   `search`, таблица на полях `AdminUniversityListItem` (§3), пагинация по
   `total`/`page`/`limit`, `programs_count` показывается как есть без
   дополнительного запроса. Клик по строке → страница деталей.
2. **Страница деталей/редактирования университета** — форма, предзаполненная
   из GET (§4), значки-замочки по `admin_locked_fields` (§7), PATCH отправляет
   только dirty-поля (§5, критично!). Вложенная таблица программ из
   `detail.programs` со ссылкой на редактирование каждой.
3. **Страница/модалка редактирования программы** — структурированные
   контролы под булевы `needs_*`-ключи и `exams`/`notes` внутри `requirements`,
   плюс `application_close` внутри `deadlines` — **не сырое JSON-поле**,
   именно из-за риска затирания в §6.
4. Обеим формам стоит завести общий хелпер вида
   `buildPatchBody(dirtyFields)`, а не дублировать логику диффа — то же
   правило "только реально изменённые поля" одинаково критично и для
   университета, и для программы.

## 10. Что не реализовано

- **Нет создания/удаления** университетов и программ — только чтение и PATCH
  (в `app/routers/admin.py` нет `POST`/`DELETE` на эти ресурсы).
- **Нет эндпоинта снятия лока** — по решению из `docs/admin-edit-lock-plan.md`
  ("no unlock endpoint for now") снять `admin_locked_fields` можно сейчас
  только прямым вмешательством в БД, не из UI.
- **Нет редактирования контента вопросников** (RIASEC/BigFive/MI-банки) через
  этот API — отдельная нерешённая задача, см.
  `docs/admin-questions-content-overrides-plan.md`.
- **Нет серверного diff'а изменений** — вся логика "что реально поменялось"
  (§5 п.2, §9 п.4) должна жить на фронте, бэкенд такого не предоставляет.
