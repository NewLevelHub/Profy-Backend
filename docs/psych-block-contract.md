# ADR: контракт психологического блока в `/result`

**Тикет:** PRO-291 (эпик **PRO-282** — «Шкала лжи · Психоэмоциональный тест ·
МАК»). **Статус:** принято, реализовано в Фазе 0. **Дата:** 2026-09-09.

Связанные документы: `00-ЭПИК-PRO-282.md` (§3 режим выката, §4 принятые
решения), `docs/frontend-result-api-contract.md` (v2-форма `/result`),
методзаписки `docs/psych/methodology-*.md`.

---

## 1. Контекст и проблема

Батарея добавляет три вспомогательных слоя для очной встречи с психологом:
достоверность протокола («шкала лжи»), психоэмоциональный тест (МЦВ Собчик),
МАК. Роли «Психолог» в системе нет, и на период отладки владелец продукта
**сознательно** хочет, чтобы выводы приходили в обычный ответ `/result` и были
видны и школьнику, и админу (эпик §3).

Нужен единый контракт: **где живут эти данные, как их расчёт изолирован от
основного отчёта, и где фиксируется согласие родителя** — так, чтобы будущее
скрытие за ролью (PRO-321) было однострочным.

---

## 2. Где живут данные

### 2.1 Контейнеры на `AnalysisResult` (агрегированные выводы)

| Поле | Тип | Наполняет | До расчёта |
|---|---|---|---|
| `analysis_results.validity` | `JSONB NULL` | Фаза 1 (PRO-296…300) | `NULL` |
| `analysis_results.psychoemotional` | `JSONB NULL` | Фаза 2 (PRO-307…309) | `NULL` |

- Форму каждого блоба определяет **его фаза**, не этот тикет. Фаза 0 только
  заводит колонки (миграция `c9f21d7e4a3b`).
- **Категорически не** размазывать выводы по `analysis_results.summary` или по
  нарративным полям (`strength_cards`, `final_analysis` и т. д.). Причина —
  PRO-321 должен уметь спрятать блок, обнулив/не отдав ровно эти контейнеры и
  секции, не трогая генерацию основного отчёта.

### 2.2 МАК — без контейнера на `AnalysisResult`

У МАК **нет скоринга и нет ИИ-интерпретации** (эпик §4). Агрегировать нечего,
поэтому колонки на `AnalysisResult` под него не заводим. Секция `mac` в
`/result` собирается Фазой 3 напрямую из таблиц истории `mac_*` (лента
«стимул → карта → тексты», сравнительный вид ребёнок ↔ родитель).

### 2.3 Таблицы истории / сырых данных (создаются в своих фазах)

- `psychoemotional_run` — сырые выборы (два списка по 8 позиций), тайминги,
  флаг достоверности прохождения, версия порогов. Фаза 2.
- `mac_*` — упражнения, карты, тексты по наводящим вопросам, автор ответа
  (ребёнок/родитель для E4). Фаза 3.

Контейнер на `AnalysisResult` — это «последний посчитанный вывод для показа»;
таблицы истории — «что именно человек сделал», для перекалибровки порогов
(шкала лжи — после ≥300–500 прохождений, МЦВ — после ≥500).

---

## 3. Схема `/result` (`app/schemas/result_v2.py`)

> Тикет называет файл `app/schemas/result.py`; фактический student-facing
> контракт живёт в `app/schemas/result_v2.py` (`result.py` был переименован
> при редизайне отчёта, см. `docs/result-report-redesign-plan.md`). Работаем
> с `result_v2.py`.

`_ResultResponseBase` получил три опциональных поля, `None` по умолчанию:

```python
validity: ValiditySection | None = None
psychoemotional: PsychoEmotionalSection | None = None
mac: MacSection | None = None
```

- Модели секций (`ValiditySection`, `PsychoEmotionalSection`, `MacSection`) —
  **каркас**: сейчас в каждой только `consent_ok: bool` (см. §5). Каждая фаза
  дополняет свою модель конкретными полями (`model_config = {"extra":
  "forbid"}` — расширение только явным добавлением полей).
- Дефолт `None` → уже закэшированные до этого изменения ответы
  десериализуются без ошибки (`ResultV2Adapter.validate_json`) — тот же
  приём, что для `EXPLORATION_CLOSING_NOTE` и пр.
- Название «Люшер»/«Lüscher» в схеме и в текстах не используется — только
  «Психоэмоциональный тест» (эпик §4).

---

## 4. Изоляция расчёта

Основной отчёт (RIASEC/BigFive/MI + нарратив) **генерируется и отдаётся
всегда**, независимо от психоблока (эпик §4, ТестЛжи §3.7).

Реализация — `report_service`:

- `build_report()` / `get_report()` — публичные входные точки. Они:
  1. строят/читают основной отчёт (`_build_report()` / `_get_report()` — без
     изменений по сути), **кэшируют именно его** (Redis `report:v2:{id}`);
  2. затем вызывают `_attach_psych_sections()`.
- `_attach_psych_sections()` прогоняет три билдера
  (`_build_validity_section`, `_build_psychoemotional_section`,
  `_build_mac_section`) — **каждый в отдельном `try/except`**. Исключение
  логируется (`logger.exception`), секция остаётся `None`, основной отчёт
  возвращается нетронутым.
- Билдеры Фазы 0 возвращают `None` (движков ещё нет). Это **единственные
  швы**, куда подключаются Фазы 1/2/3 — новых call-site в `build_report()`
  добавлять не нужно.
- Секции **не кладутся в кэш** основного отчёта — они пересобираются на
  каждый запрос. Это держит кэш независимым от зрителя (нужно к PRO-321) и
  стоит одного дешёвого `SELECT` по `consents` на запрос. При потоке
  10–15 чел./мес (эпик §2) — приемлемо; при росте нагрузки кэш секций
  вводится отдельно.

Тест-инвариант: `tests/integration/test_psych_sections_in_result.py`
(`test_main_report_survives_a_broken_psych_block_calculation`).

---

## 5. Согласие (`consent`)

- Модель `app/models/consent.py` (`consents`): `id`, `user_id` (FK,
  CASCADE), `signed_by` (строка — «Родитель: …» / «Законный
  представитель»), `scope` (строка, сейчас единственное значение
  `psych_block` — константа `CONSENT_SCOPE_PSYCH_BLOCK`), `assessment_id`
  (nullable FK; `NULL` = согласие на все прохождения этого пользователя),
  `signed_at`, `created_at`. Уникальности нет — допускаются повторные
  подписи / по-ассессментные записи.
- Сервис `app/services/consent_service.py` (RORO, `async def`):
  - `record_consent(db, *, user_id, signed_by, scope=…, assessment_id=None)`
    — `flush`, коммитит вызывающая транзакция;
  - `has_consent(db, *, user_id, scope=…, assessment_id=None)` — `bool`;
    «бланкетная» запись (`assessment_id IS NULL`) удовлетворяет любой
    запрошенный `assessment_id`.
- **Согласие ничего не блокирует в MVP** (эпик §4). Секции отчёта несут
  `consent_ok: bool` как пометку — значение приходит из `has_consent()`,
  вычисляется один раз в `_attach_psych_sections()` и передаётся во все
  билдеры. Промоушен до жёсткого предусловия (если понадобится) — точечное
  изменение внутри этих функций, call-site трогать не нужно.
- Покрытие: `tests/integration/test_consent_service.py`.

---

## 6. Резолвер видимости и задел под PRO-321

### 6.1 `psych_sections_for(viewer, *, assessment_id) -> bool`

**Единственное** место, где решается, включать ли секции психоблока в ответ
`/result` (`report_service`). Сейчас:

```python
def psych_sections_for(viewer: User | None, *, assessment_id: uuid.UUID) -> bool:
    return True  # MVP (эпик §3): выводы видны и школьнику, и админу
```

PRO-321 сузит это **до одной строки**:

```python
    return viewer is not None and viewer.role in (
        UserRole.psychologist, UserRole.admin
    )
```

Больше нигде (роутер, ассемблер, схема) видимость секций не решается.

### 6.2 `User.role`

`app/models/user.py`: `UserRole(str, Enum) = user | staff | psychologist |
admin`, колонка `users.role` (`server_default 'user'`, миграция
`c9f21d7e4a3b`). Существующие `is_admin=True` бэкфилятся в `role='admin'`.

**Ничего ещё не ограничивает по `role`.** `is_admin` остаётся источником
истины для админ-проверок (`get_current_admin_user`). Поле добавлено
исключительно чтобы §6.1 у PRO-321 был однострочным. Если команда против
колонки сейчас — откатить миграцию и модель, оставить здесь TODO-якорь:
`TODO(PRO-321): ввести User.role перед скрытием психоблока за ролью`.

---

## 7. Что делает PRO-321 (отложено, вне этого тикета)

- Меняет `psych_sections_for` на проверку роли (§6.1).
- Вводит зависимость `require_psych_access` для будущих psychologist-only
  эндпоинтов (экран разбора клиента, PRO-320).
- Обнуляет/не отдаёт контейнеры `validity`/`psychoemotional` и секции
  `validity`/`psychoemotional`/`mac` школьнику.
- Один PR, легко откатить: данные уже в структурно-отделимых
  полях/таблицах (§2), нарратив основного отчёта их не содержит.

---

## 8. Затронутые файлы (Фаза 0 / PRO-291)

| Файл | Изменение |
|---|---|
| `alembic/versions/c9f21d7e4a3b_psych_block_foundation.py` | миграция: `users.role` + enum, `analysis_results.validity/psychoemotional`, таблица `consents` |
| `app/models/user.py` | `UserRole`, `User.role` |
| `app/models/consent.py` | новая модель + `CONSENT_SCOPE_PSYCH_BLOCK` |
| `app/models/analysis_result.py` | контейнеры `validity`, `psychoemotional` |
| `app/models/__init__.py` | регистрация `Consent` |
| `app/schemas/result_v2.py` | `ValiditySection`/`PsychoEmotionalSection`/`MacSection` + 3 опциональных поля |
| `app/services/consent_service.py` | `record_consent`, `has_consent` |
| `app/services/report_service.py` | `psych_sections_for`, `_attach_psych_sections`, 3 билдера-шва, тонкие обёртки `build_report`/`get_report` |
| `app/routers/result.py` | прокидывает `viewer=current_user` |
| `tests/integration/test_psych_sections_in_result.py` | позитивный инвариант + изоляция |
| `tests/integration/test_consent_service.py` | `has_consent` под тестом |
