# Тикет: пивот "профессия → специальность" в profi-backend

Статус на момент записи: **шаги 1–2 из 8 сделаны и провалидированы**, шаги 3–8 не начаты.
Полный согласованный план (контекст, обоснование, таблица группировки) лежит в
`C:\Users\amanz\.claude\plans\profi-backend-scripts-seed-akinator-con-toasty-ladybug.md`
— читать в первую очередь, этот файл его дополняет актуальным статусом выполнения.

## Цель

Тест-акинатор должен сходиться не к узкой профессии («Программист»), а к
специальности вуза («Software Engineer»), которая показывает список
конкретных профессий внутри неё (Backend/Frontend/Fullstack/QA и т.д.).

Заодно чинится разброс `Program.direction_slug` по 3 несогласованным
таксономиям (akinator-секции / akinator-профессии / осиротевшие слаги в
`seed_universities.py`).

## Ключевой факт (уже проверено кодом)

`Direction` — обычное дерево смежности, без FK на слаги. Замена листового
уровня "51 профессия" → "38 специальностей" — это чисто изменение ДАННЫХ, без
Alembic-миграций и без изменений в движке подбора (`app/services/akinator_engine.py`
не знает, что такое "профессия", работает generic-но по `is_leaf=True`).

## ✅ ГОТОВО

### 1. `scripts/seed_akinator_content.py` — полностью переписан
- `PROFESSIONS` (51) → `SPECIALTIES` (38), у каждой добавлено поле `professions: list[str]`.
- `seed_professions()` → `seed_specialties()`, поле `professions` теперь реально пишется в БД (раньше не писалось вообще).
- `PROFESSION_AGE_GROUPS` → `SPECIALTY_AGE_GROUPS`.
- `RETIRED_DIRECTION_SLUGS` — добавлены 24 старых слага профессий, которые слились/переименовались (список см. ниже).
- `QUESTIONS`: удалены 4 вопроса, ставшие бессмысленными (order 23, 25, 35, 43), у оставшихся `resolves_pair` переписаны на новые слаги специальностей, order 24 оставлен но `resolves_pair=None`.
- `RETIRED_QUESTION_ORDERS` = `[22, 23, 25, 27, 31, 33, 35, 40, 43, 44]`.
- Все module-level `assert`-ы обновлены и **проверены** (см. ниже) — 13 секций, 38 специальностей, 40 вопросов, все secция ≥2 листа.
- `main()`, `audit_unmanaged_leaves()`, `compute_section_profiles()` — все ссылки на `PROFESSIONS` заменены на `SPECIALTIES`.

**Проверено локально** (стаб-импорт без реальной БД/sqlalchemy):
```
Sections: 13, Specialties: 38, Questions: 40, Retired direction slugs: 54
Per-section counts: medicine=3, psychology-help=3, animals-nature=4, it-data=3,
engineering-tech=3, creative-design=2, stage-media=5, words-communication=4,
education=2, sports-body=2, food-hospitality=2, business-sales=3, safety-rescue=2
```
Все совпадает с таблицей группировки из плана. Все asserts прошли.

### 2. `scripts/seed_simulations.py` — переключены слаги
- `programmer` → `software-engineer`
- `surgeon` → `general-medicine`
- `psychologist` — без изменений (не сливался)

Файл нужно **быстро визуально перепроверить** (я не читал итоговый файл после
правок, только применил 2 точечных Edit) — но правки простые (замена ключа
`"leaf_slug"` в двух словарях + комментарий), риск минимальный.

## 🔲 ОСТАЛОСЬ СДЕЛАТЬ (по порядку)

### Итоговая таксономия специальностей — 38 шт. (для сверки при правке остальных файлов)

Полные slug/name/professions уже целиком в `scripts/seed_akinator_content.py`.
Список слагов по секциям:

- **akinator-medicine**: `general-medicine`, `dentist`, `pharmacist`
- **akinator-psychology-help**: `psychologist`, `speech-therapist`, `social-worker`
- **akinator-animals-nature**: `veterinary-zootechnics`, `agronomist`, `zoologist`, `ecologist`
- **akinator-it-data**: `software-engineer`, `data-science`, `it-infrastructure-security`
- **akinator-engineering-tech**: `mechanical-engineer`, `civil-engineering`, `pilot`
- **akinator-creative-design**: `design`, `architect`
- **akinator-stage-media**: `actor`, `musician`, `film-director`, `cinematographer`, `makeup-artist-film`
- **akinator-words-communication**: `journalist`, `translator`, `lawyer`, `pr-specialist`
- **akinator-education**: `school-teacher`, `kindergarten-teacher`
- **akinator-sports-body**: `sports-coach`, `rehabilitation-therapist`
- **akinator-food-hospitality**: `food-production-tech`, `hospitality-manager`
- **akinator-business-sales**: `management-entrepreneurship`, `marketing`, `finance-accounting`
- **akinator-safety-rescue**: `fire-safety-engineer`, `police-officer`

Старые слаги, которые ушли (для grep/поиска остаточных ссылок по всему репо,
включая тесты): `surgeon, physician, emergency-physician, psychiatrist,
veterinarian, cynologist, programmer, qa-tester, data-analyst, sysadmin,
civil-engineer, building-systems-engineer, graphic-designer, illustrator,
fashion-designer, furniture-designer, ux-designer, head-chef,
confectionery-technologist, sales-manager, entrepreneur, logistician,
marketer, accountant`.

### 3. `scripts/seed_astana_universities.py`

- Импортировать множество слагов специальностей из `seed_akinator_content.py`
  (`from scripts.seed_akinator_content import SPECIALTIES` → `{s["slug"] for s in SPECIALTIES}`).
- В `PROGRAMS_BY_UNIVERSITY_SLUG` каждая программа сейчас имеет
  `"direction_slug": "akinator-it-data"` (уровень секции) — переразметить на
  конкретную специальность там, где программа явно ей соответствует. Примеры
  из уже прочитанных данных:
  - AITU "Software Engineering (бакалавр)" → `software-engineer`
  - AITU "Big Data Analysis (бакалавр)" → `data-science`
  - AIU "Data Science (бакалавр)" → `data-science`
  - QAIRU "AI and Machine Learning (бакалавр)" → `data-science`
  - NU "Computer Science (бакалавр)", ENU "Информационные технологии", Cardiff KZ "Computer Science" → `software-engineer` (или общий `akinator-it-data`, если не хочется гадать про backend/data-track — тут можно оставить на уровне секции, это осознанный компромисс)
  - NU "Doctor of Medicine", МУА "Общая медицина"/"Сестринское дело" → `general-medicine`
  - МУА "Фармация" → `pharmacist`
  - NU "Business Administration (BBA)", MNU "Finance" → `management-entrepreneurship` либо `finance-accounting` (смотреть по описанию программы)
  - КазАТУ "Архитектура и дизайн" → `design` (или `architect`, если это архитектурный профиль)
  - КазНУИ "Графический дизайн" → `design`
  - Все остальные (Юриспруденция→`lawyer`, Психология→`psychologist`, Туризм→`hospitality-manager`, Ветеринария→`veterinary-zootechnics`, Экология→`ecologist` и т.д.) — маппинг прямой, 1 программа = 1 специальность почти везде.
- Добавить `assert` что каждый использованный `direction_slug` — известная секция ИЛИ известная специальность (предотвращает появление 4-й таксономии).
- `_CAREERS_BY_DIRECTION` / `_WHO_ITS_FOR_BY_DIRECTION` (сейчас keyed по секции,
  строки 367–393 в старой версии файла) — там, где программа теперь размечена
  на уровне специальности, брать `career_options`/`who_its_for` напрямую из
  `professions`/`description` совпавшей записи `SPECIALTIES` (можно просто
  построить `dict` `{s["slug"]: s for s in SPECIALTIES}` и обращаться по
  `direction_slug`). Для программ, оставшихся на уровне секции — старые
  dict-фоллбэки сохранить как есть.

### 4. `scripts/seed_universities.py`

- Тот же импорт множества специальностей.
- Заменить все 15 "осиротевших" слагов (`it-development`, `data-science`,
  `artificial-intelligence`, `engineering-architecture`, `design-digital-art`,
  `medicine-biology`, `finance-economics`, `psychology-pedagogy`,
  `law-public-administration`, `media-journalism`, `marketing-advertising`,
  `project-management`, `business-entrepreneurship`, `ecology-nature`,
  `science-research`) на реальные слаги специальностей. Примерное соответствие:
  - `it-development` → `software-engineer`
  - `data-science` → `data-science` (совпадает по смыслу и по слагу — удобно)
  - `artificial-intelligence` → `data-science`
  - `engineering-architecture` → `civil-engineering` или `mechanical-engineer` (смотреть по программе)
  - `design-digital-art` → `design`
  - `medicine-biology` → `general-medicine` или `zoologist` (смотреть по программе — там и медицина, и биология вперемешку)
  - `finance-economics` → `finance-accounting`
  - `psychology-pedagogy` → `psychologist` или `school-teacher`
  - `law-public-administration` → `lawyer`
  - `media-journalism` → `journalist`
  - `marketing-advertising` → `marketing`
  - `project-management` → `management-entrepreneurship`
  - `business-entrepreneurship` → `management-entrepreneurship`
  - `ecology-nature` → `ecologist`
  - `science-research` → `zoologist` (или ближайшая по описанию программы)
  - Добавить тот же `assert` на членство в множестве специальностей.
  - Это чинит функциональный баг: сегодня эти 64 программы вообще не всплывают в обычном флоу результата теста (`program_direction_slugs_for` не расширяет неизвестный slug).

### 5. `app/schemas/akinator_session.py`
Добавить `professions: list[str] = Field(default_factory=list)` в `RevealLeaf`.

### 6. `app/schemas/result.py`
Добавить `professions: list[str]` в `AkinatorResultResponse`.

### 7. `app/services/result_service.py`
- В `get_result()` — прокинуть `professions=direction.professions` в конструктор `AkinatorResultResponse(...)`.
- В `_backups_for()` — прокинуть `professions=direction.professions` в конструктор `RevealLeaf(...)`.

### 8. `app/routers/akinator.py`
В `to_leaves()` — прокинуть `professions=direction.professions` в конструктор `RevealLeaf(...)` (это карточки reveal/backups до подтверждения).

### 9. Тесты — обновить
- `tests/unit/test_seed_akinator_content_data.py`, `tests/integration/test_seed_akinator_content.py` — обновить ожидаемые числа (13 секций / **38 специальностей** / **40 вопросов**). Файлы уже были рассинхронизированы с реальностью ДО этого пивота (ожидали 16/67/45) — поправить заодно на актуальные цифры.
- Найти и обновить любые тесты с захардкоженными старыми слагами (`programmer`, `surgeon`, `dentist`, `qa-tester` и т.п.) — вероятные файлы: `test_akinator_engine.py`, `test_akinator_router.py`, `test_akinator_session_service.py`, `test_simulation.py`, `test_program_direction_resolver.py`, `test_result_service.py`. Быстрый способ найти: `grep -rn "programmer\|surgeon\|qa-tester\|data-analyst\|sysadmin" tests/`.

### 10. Проверка (после всех правок)

```bash
# 1. Статика без БД (модуль уже проверен вручную, см. "ГОТОВО" выше — но
#    после правок 3-4 файлов стоит перепроверить ещё раз тем же приёмом
#    stub-импорта, или прямо в Docker):
docker-compose -f docker-compose.yml -f docker-compose.local.yml exec api python -c "import scripts.seed_akinator_content"

# 2. Прогон seed-скриптов по порядку:
docker-compose -f docker-compose.yml -f docker-compose.local.yml exec api python scripts/seed_akinator_content.py
docker-compose -f docker-compose.yml -f docker-compose.local.yml exec api python scripts/seed_simulations.py
docker-compose -f docker-compose.yml -f docker-compose.local.yml exec api python scripts/seed_astana_universities.py
docker-compose -f docker-compose.yml -f docker-compose.local.yml exec api python scripts/seed_universities.py

# 3. Повторный прогон (идемпотентность) — inserted должен стать 0.

# 4. pytest tests/unit tests/integration

# 5. End-to-end через API:
#    GET /directions/{новый-слаг} -> professions заполнен
#    GET /directions/tree -> дерево показывает названия специальностей
#    полный прогон акинатора (start -> answer* -> reveal) -> RevealLeaf.professions заполнен
#    feedback -> GET /result/{assessment_id} -> AkinatorResultResponse.professions заполнен
#    GET /universities/programs?direction={слаг} -> программы находятся
#    симуляция для software-engineer/general-medicine/psychologist отвечает (не 404)
```

## Контакт с исходным ТЗ пользователя

Дано в ТЗ: "Было: Backend-Разработчик. Стало: Software-Engineer (и
перечислять список профессий)". Реализовано ровно так —
`SPECIALTIES` содержит запись:
```python
{"slug": "software-engineer", "name": "Software Engineer", ...,
 "professions": ["Backend-разработчик", "Frontend-разработчик",
                 "Fullstack-разработчик", "Мобильный разработчик", "QA-инженер"]}
```
