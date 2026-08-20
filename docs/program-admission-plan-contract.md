# План: план поступления по конкретной программе на странице направления

Дата: 2026-08-18. Автор: обсуждение с владельцем продукта (сессия Frontend,
Profy-Frontend), исследование кода проведено прямым чтением обоих
репозиториев (Profy-Frontend и Profy-Backend) — не пересказ.

Статус: **план зафиксирован, реализация не начата.** Это справочный
документ для следующей сессии реализации на бэке и фронте — в нём написано,
что и где менять, но код ещё не тронут. Копия этого файла лежит в обоих
репозиториях по одному и тому же пути:
`docs/program-admission-plan-contract.md`.

---

## 0. Проблема и цель

Сейчас страница `/results/directions/:slug` (`DirectionDetailPage.tsx` на
фронте) уже показывает заголовок направления, `why`/`matched_strengths`
(ровно то, что нужно), список навыков/предметов и карточку «попробуй
сейчас» — но:

- список университетов/программ живёт на отдельной странице
  (`/results/directions/:slug/universities`), доступной только по клику на
  кнопку «Найти университеты»;
- «roadmap по направлению» (`/results/directions/:slug/roadmap`,
  `DirectionRoadmapPage.tsx`) генерируется только по `direction_slug`, без
  привязки к конкретному университету/программе;
- нет никакой обратной связи вида «для поступления сюда нужна математика и
  физика — у тебя это уже сильная сторона» / «стоит подтянуть, ты сам
  отметил их как сложные».

Цель: собрать это в один связный флоу на странице направления — направление
+ почему подходит → сразу список университетов/программ → выбор одной
программы → генерация плана поступления именно под неё, с опорой на
предметы, которые студент указал на онбординге.

## 1. Ключевая находка, которая определяет весь план

**В бэкенде нигде нет структурированных данных «какие предметы нужны для
программы».** `Program.requirements` — свободный JSONB-словарь, и для
реального набора из 55 засеянных университетов (`scripts/seed_kz_universities.py`,
`university-data/almaty_universities_data.py` /
`astana_universities_data.py`) он содержит только `{"notes": [...]}` —
свободный текст на русском **на уровне университета** (один и тот же список
дублируется на все специальности этого вуза), например:

```
"IT/математика: Математика + Физика или Информатика."
"Биология/экология: Биология + Химия."
```

Модели `Subject`/справочника предметов не существует нигде в бэкенде
(`grep -rln "class Subject" app/models` — пусто). Более богатый датасет
(`seed_universities.py`, с `min_gpa`/`exams`/`min_ielts` по каждой
программе) был удалён 2026-08-13 — текущий источник истины только
`{"notes": [...]}`.

**Решение (согласовано с владельцем продукта):** не строить структурный
справочник предметов и не мигрировать/размечать данные вручную. Вместо
этого — отдать свободный текст `requirements.notes` конкретной программы и
все четыре предметных списка студента (`subjects_liked`, `subjects_disliked`,
`subjects_easy`, `subjects_hard`) в LLM внутри уже существующего пайплайна
генерации `direction_roadmap`, и попросить модель сформулировать
обоснованный фидбэк по предметам — по той же схеме, что уже используется
для остального содержимого roadmap (generate → validate → retry, без
выдумывания фактов).

## 2. Что уже есть и переиспользуется — не трогаем

- `DirectionDetailPage.tsx`: блок `why`/`matched_strengths` — уже ровно то,
  что нужно, без изменений.
- `universityApi.getPrograms(slug)` / `ProgramCard` — переиспользуются,
  просто переносятся в другое место на странице (не переписываются с нуля).
- Весь пайплайн `direction_roadmap` (`app/services/roadmap_builder.py`,
  `app/prompts/direction_roadmap.py`, `llm_client.complete_json` → валидация
  → один повтор, без деterministic-фолбэка) — расширяется, не заменяется.
- `SubjectsGapSection.tsx` на фронте (клиентское нечёткое сравнение
  `roadmap.subjects_to_focus` с `subjectsEasy`) — остаётся как есть, это
  отдельный, уже существующий механизм для списка предметов на уровне
  направления. Новый функционал (фидбэк по предметам конкретной программы)
  — параллельный, не заменяет его.
- Уникальный констрейнт `(assessment_id, direction_slug)` на
  `direction_roadmaps` — не меняется. Один roadmap на направление; при
  повторной генерации с другой программой строка перезаписывается (см. §3).

## 3. Изменения в бэкенде (Profy-Backend)

### 3.1 `app/models/direction_roadmap.py`

Добавить nullable `program_id: UUID | None` (FK → `programs.id`) в
`DirectionRoadmap`. Уникальный констрейнт `(assessment_id, direction_slug)`
**не менять** — это по-прежнему одна запись на направление; `program_id` —
дополнительный факт на этой же строке. Если студент выберет другую
программу позже, повторная генерация обновляет ту же строку (это
согласованное решение — никакой отдельной сущности «план на программу» не
вводим).

Новая Alembic-миграция на добавление колонки (+ индекс по `program_id`, если
понадобится выборка по нему).

### 3.2 `app/schemas/roadmap.py`

Запрос на генерацию (тело `POST /roadmap/direction`) — добавить
опциональный `program_id: UUID | None`.

`DirectionRoadmapResponse` — добавить опциональное поле `program_fit`:

```python
class SubjectFit(BaseModel):
    subject: str
    # Название ровно как оно встречается в тексте требований программы —
    # не из справочника (справочника нет).
    status: Literal["strength", "needs_work", "unclear"]
    note: str
    # Обоснование, опирающееся на subjects_liked/disliked/easy/hard
    # студента — не выдумка модели.

class ProgramFit(BaseModel):
    program_id: UUID
    program_name: str
    university_name: str
    subjects: list[SubjectFit]
    summary: str  # 1-2 предложения общего вывода о соответствии


class DirectionRoadmapResponse(BaseModel):
    ...  # существующие поля без изменений
    program_fit: ProgramFit | None = None
```

`program_fit` = `null`, когда roadmap сгенерирован без `program_id` —
полностью обратная совместимость, старые клиенты не увидят изменений формы.

### 3.3 `app/routers/roadmap.py`

`POST /roadmap/direction`: принять `program_id`. Если передан — загрузить
`Program` (404, если не найдена) и проверить, что `direction_slug` входит в
`program.profession_slugs` (400 при несовпадении — та же логика проверки
целостности, что уже используется в этом роутере для других полей).

`GET /roadmap/{assessment_id}/directions/{slug}` — сигнатура не меняется,
просто в ответе появляется `program_fit`, если он был сохранён при
генерации.

### 3.4 `app/services/roadmap_builder.py`

В `generate_direction_roadmap()` (или там, где строится контекст для
промпта): при наличии `program_id` —
1. загрузить `Program` + связанный `University` (`program.university`);
2. взять `program.requirements` (в текущих данных — `{"notes": [...]}`)
   как есть;
3. добавить это в контекст, который уходит в LLM, вместе со всеми четырьмя
   предметными списками студента из `Profile` — **перед реализацией
   проверить**, все ли четыре поля (`subjects_liked`, `subjects_disliked`,
   `subjects_easy`, `subjects_hard`) уже присутствуют в `StudentContext`
   (`app/schemas/student_context.py`) — по имеющемуся исследованию профиль
   уже в целом дампится в контекст, но это нужно перепроверить прямым
   чтением файла на момент реализации, а не полагаться на этот документ.

Пайплайн генерации — тот же `llm_client.complete_json` → валидация → один
корректирующий повтор, что уже используется для `direction_roadmap`.
**Решение по поведению при недоступности LLM** (зафиксировать на моменте
реализации, не жёсткое требование этого документа): если LLM недоступна —
`program_fit` просто отсутствует в сгенерированном roadmap, а не блокирует
генерацию всего остального (основной контент roadmap важнее, чем этот
блок). У самого direction_roadmap эндпоинта сегодня в принципе нет
деterministic-фолбэка (503 при недоступности LLM) — уточнить перед
реализацией, должен ли `program_fit` следовать этому же правилу (тогда весь
запрос будет падать 503, если LLM недоступна, независимо от program_id) или
иметь собственное, более мягкое поведение. Читать
`docs/roadmap-content-generation.md` и `docs/roadmap-goal-contract.md`
перед изменением — они документируют текущий контракт retry/fallback,
который нельзя случайно сломать.

### 3.5 `app/prompts/direction_roadmap.py`

Расширить системный промпт инструкцией по фидбэку о предметах: по
свободному тексту требований программы — определить (не придумать), какие
именно предметы упоминаются, сопоставить с четырьмя списками предметов
студента, сформировать `SubjectFit[]` + `summary`. Явное анти-галлюцинация
правило в стиле уже существующих в этом файле: называть предмет только
если он реально упомянут в тексте требований; если текст не называет
конкретных предметов — вернуть пустой `subjects` и `summary`, объясняющий
это, никогда не выдумывать «типичные» требования для этой специальности по
общим знаниям модели.

### 3.6 Со стороны бэкенда фиксов не требуется

`subjects_liked`/`subjects_disliked` в бэкенде уже названы правильно — баг
только на фронте (см. §5).

## 4. Изменения на фронте (Profy-Frontend)

### 4.1 `src/pages/results/DirectionDetailPage.tsx`

- Хиро-блок (`why`/`matched_strengths`) — без изменений.
- Ниже — секция «Университеты и программы» инлайн: тот же запрос
  `universityApi.getPrograms(slug)`, что сегодня использует
  `useUniversityList`, за тем же гейтом `canSeeUniversities(goal, ageGroup)`
  (без изменений в логике доступа — правило «только senior» остаётся).
- Вынести рендер списка (фильтр по стране + грид `ProgramCard` +
  loading/empty/error-состояния) из `UniversityListPage.tsx` в общий
  компонент (например, `src/pages/results/components/ProgramListSection.tsx`),
  чтобы и инлайн-версия, и оставшаяся отдельная страница рендерились из
  одной реализации — не дублировать разметку.
- Локальный стейт `selectedProgramId`; клик по `ProgramCard` выбирает
  программу (визуально подсвечивается) вместо перехода на
  `/universities/:programId` — этот роут остаётся, но теперь достигается
  через отдельную явную кнопку «Подробнее» на карточке, а не первичным
  кликом.
- Кнопка «Построить план поступления», активна после выбора программы,
  вызывает расширенный `directionRoadmapApi.generate(assessmentId, slug,
  programId)` — при успехе переход на существующую
  `/results/directions/:slug/roadmap` (переиспользуем весь
  `DirectionRoadmapPage` целиком, не строим второй рендер roadmap инлайн).
- Убрать кнопку «Найти университеты» (её функцию теперь выполняет всегда
  видимая инлайн-секция) — сам `canSeeUniversities` остаётся гейтом уже для
  этой инлайн-секции.

### 4.2 `src/pages/roadmap/direction/DirectionRoadmapPage.tsx`

Добавить новую секцию (например,
`components/ProgramFitSection.tsx`, в стиле уже существующих
`SubjectsGapSection`/`UniversityTrackSection`), рендерящую
`roadmap.program_fit`, когда он есть: название программы/вуза, список
`SubjectFit[]` (сильная сторона / стоит подтянуть / неясно, с обоснованием
для каждого), итоговое summary-предложение. Ничего не рендерит, если
`program_fit` — `null` (план без привязки к программе, как сегодня —
поведение не меняется).

### 4.3 `src/shared/types/index.ts`

- `DirectionRoadmapResponse` — добавить `program_fit: ProgramFit | null`
  (зеркалит новую бэкенд-схему один в один).
- Исправить `ProgramBrief.direction_slug` → `profession_slugs: string[]`
  (соответствует реальному полю бэкенда — сейчас тип неверный, но нигде не
  рендерится напрямую, поэтому низкий риск; лучше исправить до того, как
  эта фича начнёт больше работать с данными программы).
- Исправить `ProfilePayload`/`ProfileResponse`: `subjects_like` →
  `subjects_liked`, `subjects_dislike` → `subjects_disliked` (см. §5).

### 4.4 `src/shared/api/directionRoadmap.ts`

```ts
generate(assessmentId: string, slug: string, programId?: string)
  → POST /roadmap/direction { assessment_id, direction_slug: slug, ...(programId && { program_id: programId }) }
```

## 5. Два попутных бага — фикс в этом же заходе

### 5.1 Несовпадение имён полей предметов

Фронт отправляет/читает `subjects_like`/`subjects_dislike`; реальные поля
модели/схемы бэкенда — `subjects_liked`/`subjects_disliked`
(`app/models/profile.py`, `app/schemas/profile.py`). Из-за этого сегодня
эти два конкретных поля **молча не доезжают ни в одну, ни в другую
сторону**: при сохранении профиля бэкенд не знает ключ `subjects_like` и
просто его игнорирует; при чтении профиля фронт ищет `profile.subjects_like`,
которого в ответе бэкенда никогда не было (там `subjects_liked`) — отсюда
эффект «не подтягивается» при повторном заходе на экран профиля/онбординга.
`subjects_easy`/`subjects_hard` не задеты — имена и так совпадают.

**Фикс — на фронте**, переименовать под уже верное бэкенд-имя (не трогать
бэкенд): `subjects_like` → `subjects_liked`, `subjects_dislike` →
`subjects_disliked`, во всех потребителях:
- `src/pages/onboarding/hooks/useProfileSetup.ts`
- где собирается финальный `POST /profile` (черновик онбординга →
  `ArtifactsSetupPage`/`useArtifactsSetup.ts`)
- `src/pages/profile/sections/SubjectsSection.tsx`
- `src/shared/types/index.ts` (см. §4.3)

### 5.2 Экран «не нравится» отсутствует в онбординге

Поле `subjects_disliked` в бэкенде есть и работает, но ни один экран
онбординга его не собирает — `useProfileSetup.ts` держит
`subjectsDislike` как `useState` без сеттера, инициализированный только из
уже существующего профиля (режим редактирования); при первом прохождении
онбординга всегда `[]`.

**Фикс**: добавить реальный `SubjectGroup` для `subjectsDislike` в
`ProfileSetupPage.tsx` (тот же каталог из 13 предметов + «+ своё», что и у
`subjectsLike`/`subjectsEasy`/`subjectsHard`) — либо третьей группой на
существующем экране `STEP_SUBJECTS_STRUGGLE`, либo отдельным шагом
(решить на реализации, по тому, насколько тесно станет с третьей группой
на одном экране). Логику «нельзя выбрать в двух группах сразу»
(`otherSelected`) стоит продумать: предмет одновременно «сложный» и «не
нравится» — нормально и ожидаемо; «лёгкий» и «не нравится» одновременно —
осознанно оставить возможным, а не блокировать молча (студент может не
любить предмет, который у него хорошо получается).

## 6. Что осознанно не делаем

- Не строим справочник/таксономию предметов (`Subject` модель).
- Не добавляем структурированное поле требований на уровне программы —
  остаётся свободный текст `requirements.notes` на уровне университета.
- Не делаем детерминированное (не-LLM) сопоставление предметов для этой
  фичи — только LLM-генерация внутри `direction_roadmap` (в отличие от
  уже существующего клиентского fuzzy-match в `SubjectsGapSection`, который
  остаётся отдельным и нетронутым механизмом для другого поля,
  `subjects_to_focus`).
- Не меняем общий (не привязанный к направлению) roadmap
  (`POST /roadmap/generate`, таблица `roadmaps`) — он не в скоупе.
- Не удаляем страницы `/universities` и `/universities/:programId` —
  список переезжает инлайн, но обе страницы остаются доступны для прямых
  ссылок.

## 7. Файлы, которые затрагиваются

**Бэкенд**: `app/models/direction_roadmap.py`, новая Alembic-миграция,
`app/schemas/roadmap.py`, `app/routers/roadmap.py`,
`app/services/roadmap_builder.py`, `app/prompts/direction_roadmap.py`.

**Фронтенд**: `src/pages/results/DirectionDetailPage.tsx`, новый
`src/pages/results/components/ProgramListSection.tsx` (вынесен из
`UniversityListPage.tsx`), `src/pages/roadmap/direction/DirectionRoadmapPage.tsx`,
новый `src/pages/roadmap/direction/components/ProgramFitSection.tsx`,
`src/shared/types/index.ts`, `src/shared/api/directionRoadmap.ts`,
`src/pages/onboarding/hooks/useProfileSetup.ts`, шаг с предметами в
`ProfileSetupPage.tsx`, `src/pages/profile/sections/SubjectsSection.tsx`.

## 8. Проверка

1. Перед изменением `roadmap_builder.py` прочитать
   `docs/roadmap-content-generation.md` и `docs/roadmap-goal-contract.md` —
   они документируют текущий контракт retry/fallback, который нельзя
   случайно сломать.
2. Бэкенд: прогнать существующие тесты roadmap (если есть в `tests/`) +
   ручной `POST /roadmap/direction` с `program_id` и без — на реальной
   засеянной программе — подтвердить, что `program_fit` появляется, когда
   ожидается, и `null` в остальных случаях; проверить, что
   анти-галлюцинационное правило промпта реально держится на настоящем
   `{"notes": [...]}` из датасета 55 университетов.
3. Фронтенд: `npx tsc --noEmit`, mechanical-скан
   (`node .claude/skills/impeccable/scripts/detect.mjs --json src/pages/results src/pages/onboarding src/pages/profile`).
4. Ручной прогон нового флоу целиком, когда обе стороны задеплоены вместе
   (это кросс-репо фича — фронт отдельно полностью не проверить без живого
   бэкенда): страница направления → инлайн-список программ → выбор одной →
   генерация плана → переход на страницу roadmap → видим
   `ProgramFitSection` с обоснованным фидбэком по предметам.
5. Подтвердить фикс бага с предметами: создать профиль с
   liked/disliked-предметами, перезагрузить `/profile`, убедиться, что оба
   поля возвращаются (сейчас — нет).
