# План развития (development plan)

AI-план развития школьника (senior, 9–11 класс) до поступления. Один сценарий:
ученик выбрал профессию и конкретную программу вуза → «Собрать план развития».

Строится **аддитивно** рядом с legacy `Roadmap` / `DirectionRoadmap` /
`direction_inquiry` — они пока не удалены (от них зависят `goal_overlay_service`
и `admin_service`; их перевод — отдельная задача).

## API

| Метод | Путь | |
|---|---|---|
| `POST` | `/api/v1/development-plan` | `{assessment_id, program_id}` → генерация или кэш |
| `GET`  | `/api/v1/development-plan/{assessment_id}/{program_id}` | сохранённый план или 404 |

Коды: `503` — LLM выключен или сбой после ретрая; `403` — не senior или чужой
assessment; `409` — нет `AnalysisResult` / направление не резолвится;
`404` — `DEVELOPMENT_PLAN_ENABLED=False` или план ещё не сгенерирован (GET).

Кэш: `devplan:v1:{assessment_id}:{program_id}`, TTL 24 ч. Инвалидируется на
пересдаче теста через `assessment_shared.invalidate_direction_flow`.

## Пайплайн

`app/services/development_plan_service.py`:

1. Guard'ы (флаг, LLM, доступ, senior, analysis, program↔direction).
2. `build_generation_input` (`development_plan_context.py`) — собирает:
   - `StudentContext` (`student_context.build_student_context`);
   - `AdmissionFacts` = `university_requirements.map_program_requirement` +
     `is_foreign` (страна вуза ≠ Казахстан) + `foreign_route` / `language_exam`
     (общий текст по стране) + `source_url` / `last_verified` (из
     `Program.fact_sources` / `University.fact_sources`);
   - `subjects_needed` = профильные предметы из `exams` (нормализованы к
     `CANONICAL_SUBJECTS`) + обязательные ЕНТ;
   - `curriculum_slices` по каждому предмету (см. ниже);
   - `stage_slots` по `grade` (`prompts/development_plan.py::STAGE_SLOTS`).
3. **Фаза 1 — скелет** (1 вызов LLM): `target`, `about_you` (в т.ч. зона роста
   с `evidence`), `skills`, 4 этапа по 3–4 задачи `{track, title, why,
   done_when}` без шагов. Валидатор `valid_skeleton`, 1 корректирующий ретрай.
4. **Фаза 2 — раскрытие** (4 вызова, `asyncio.gather`): по этапу → `steps[]` с
   `actions[]` (`text`, `time`, `kind` ∈ `once|repeat|project`, `count_target`).
   Валидатор `valid_stage`, 1 ретрай на каждый этап. Любой невосстановимый
   сбой → `503`, частичный план не отдаём.
5. Сборка `DevelopmentPlanResponse`, upsert `development_plans`, кэш.

Зона роста: LLM сама выводит, что профессия требует по характеру, и пересекает
с подтверждёнными слабыми сторонами ученика (слабые буквы RIASEC + низкие черты
`personality_notes` + трудные нужные предметы). Отдельного справочника
диспозиций нет.

## Справочник школьных тем — `app/data/kz_curriculum_bank.py`

Статический модуль, импортируется напрямую (без таблицы и seed). Формат и
источники — в докстринге файла. Контент-команда наполняет по образцу; код
работает при частичном справочнике (нет ключа → `curriculum_slice` = `None`,
промпт говорит «по стандартной программе РК»).

`curriculum_slice(subject, grade, month)` → `{catchup, ahead}`:
- `ahead` — темы с `quarter >= текущей четверти`, первые 4;
- `catchup` — последние 3 темы прошлого класса;
- никаких утверждений о реальном положении класса, без веса ЕНТ.

## Конфиг (`app/config.py`)

`LLM_DEVPLAN_MODEL` (`gpt-4.1`), `LLM_DEVPLAN_TIMEOUT`,
`LLM_DEVPLAN_SKELETON_MAX_TOKENS`, `LLM_DEVPLAN_STAGE_MAX_TOKENS`,
`DEVELOPMENT_PLAN_ENABLED` (по умолчанию `False` — фича 404-ит).

## Фронт

`src/pages/roadmap/plan/` — desktop-first (4-колоночный таймлайн на `lg`,
аккордеон ниже). Прогресс по микрошагам — `store/planProgress.ts`
(Zustand `persist`, localStorage, без бэкенда). Кнопка «Собрать план развития»
на `ProgramDetailPage` (только senior).

## Тесты

- `tests/unit/test_development_plan_validation.py`, `..._curriculum.py` — чистые.
- `tests/integration/test_development_plan_service.py` — LLM замокан, нужен
  Docker DB.

## Открытые вопросы

- Справочник тем: РК-only или добавить РФ-программу для русскоязычных школ.
- `foreign_route` / `language_exam`: сейчас общий текст по стране; можно вынести
  в поле на `University`.
- Перевод `goal_overlay_service` / `admin_service` с legacy `Roadmap` и удаление
  `direction_roadmaps` / `direction_inquiries`.
