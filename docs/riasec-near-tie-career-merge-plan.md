# RIASEC: близкий разрыв баллов — объединять подобранные профессии, а не выбирать один код вслепую

## Контекст

При разборе, почему на проде для одного и того же профиля RIASEC (R=43,
I=53, A=47, S=79, E=46, C=53) выдавался совершенно другой топ-10 профессий,
чем локально, была найдена причина: `top_code()`
(`app/services/riasec_service.py:109-113`) выбирает топ-3 буквы по
«сырому» числовому баллу **без порога значимости** — тай-брейк по
`HOLLAND_ORDER` срабатывает только при *точном* равенстве баллов.
Отображаемые I=53/C=53 — округлённые значения; реальные значения почти
наверняка отличаются на доли балла (например, 52.9 против 53.1).
Воспроизведение прод-результата это подтвердило: то, какая из букв I/C
оказывается чуть выше, переворачивает весь трёхбуквенный код (`S-I-C` vs
`S-C-I`). А поскольку `career_match_score`/`matched_careers`
(`app/services/riasec_service.py:130-161`) сильно взвешивают позицию буквы
в коде (1-е место ×3, 2-е ×2, 3-е ×1), а каталог направлений распределён по
перестановкам неравномерно (для любой перестановки {S,I,C} в базе всего по
2 направления, тогда как вокруг C-S-* — плотный кластер), разница в доли
балла, невидимая студенту (оба значения отображаются как «53»), приводит к
двум почти полностью непересекающимся топ-10 спискам профессий. Студент же
видит один уверенно поданный список без каких-либо признаков того, что это
был, по сути, случайный выбор.

**Почему это нужно исправить:** алгоритм не сломан — он делает ровно то,
что в нём заложено, — но подача случайного тай-брейка как уверенного,
единственного результата переоценивает точность самоотчётного теста из
20-40 вопросов по шкале Лайкерта. Когда два (или больше) кода одинаково
правдоподобны, честный ответ — список профессий, отражающий оба варианта,
а не один, выбранный произвольно из-за правила тай-брейка, которое студент
даже не видит.

**Решение (согласовано с пользователем):** объединять, а не показывать
раздельно. Когда соседние ранги близки по баллу, считаем подбор профессий
для всех правдоподобных порядков букв и объединяем их в *тот же самый*
единый ранжированный список (каждое направление сохраняет свой лучший балл
среди рассмотренных вариантов кода) — без новых полей схемы, без новой
концепции в UI; `report_v2_assembler.py`/`StudentCareer` не меняются.

Подтверждено вне рамок задачи: у junior/MI подбора профессий вообще нет
(`app/services/mi_service.py`, ветка junior в `report_service.py` всегда
ставит `careers = []`) — это касается только RIASEC (middle/senior).

## Дизайн решения

### 1. `app/services/riasec_service.py`

Добавить константу порога рядом с `top_code`:

```python
# Разрыв такого размера (в процентных пунктах) меньше того, что видно
# студенту при округлении до целого («53» против «53»), и находится в
# пределах шума самоотчётного теста из ~20-40 пунктов по Лайкерту. Ниже
# этого порога соседние ранги считаются равными, а не доверяем тому, какой
# из них на доли балла выше.
_NEAR_TIE_THRESHOLD = 2.0
```

Добавить `candidate_codes()`, построенную на том же списке `ranked`, который
уже вычисляет `top_code` (вынести общую сортировку в отдельную функцию,
не дублировать её):

```python
def _ranked_types(normalized: dict[str, float]) -> list[str]:
    return sorted(HOLLAND_ORDER, key=lambda t: (-normalized.get(t, 0.0), HOLLAND_ORDER.index(t)))

def top_code(normalized: dict[str, float], limit: int = 3) -> list[str]:
    return _ranked_types(normalized)[:limit]

def candidate_codes(normalized: dict[str, float], limit: int = 3) -> list[list[str]]:
    """Результат `top_code`, плюс по одному альтернативному порядку для
    каждой соседней пары внутри топ-`limit`, чьи баллы отличаются меньше
    чем на `_NEAR_TIE_THRESHOLD` — меняем местами ранги 1↔2 и/или 2↔3
    независимо (не одновременно), если каждая пара сама по себе близка по
    баллу. Основной код всегда идёт первым. См. docs/senior-report-algorithm.md
    §1.3, почему это нужно."""
    ranked = _ranked_types(normalized)
    primary = ranked[:limit]
    variants = [primary]
    for i in range(limit - 1):
        a, b = primary[i], primary[i + 1]
        if abs(normalized.get(a, 0.0) - normalized.get(b, 0.0)) < _NEAR_TIE_THRESHOLD:
            swapped = list(primary)
            swapped[i], swapped[i + 1] = swapped[i + 1], swapped[i]
            variants.append(swapped)
    # Убираем дубликаты (например, плоский топ-3 иначе мог бы повториться),
    # сохраняя порядок.
    seen: set[tuple[str, ...]] = set()
    out = []
    for code in variants:
        key = tuple(code)
        if key not in seen:
            seen.add(key)
            out.append(code)
    return out
```

Изменить `matched_careers`, чтобы она принимала список кандидатов-кодов и
объединяла результаты по лучшему баллу на каждое направление. Единственный
вызывающий код в продакшене — `report_service.py:769`, так что это прямое
изменение сигнатуры, а не дополнительная перегрузка. Но
`tests/integration/test_content_locale.py::test_directions_kk_names_and_shared_slug`
(строки 140-144) тоже вызывает её напрямую с одним плоским кодом
(`code = ["I", "R", "C"]`) и потребует правки — передавать `[code]`:

```python
async def matched_careers(
    user_codes: list[list[str]], db: AsyncSession, limit: int = 10
) -> list[tuple[Direction, int]]:
    directions = (await db.execute(select(Direction))).scalars().all()
    scored = [
        (d, max(career_match_score(code, d.holland_code) for code in user_codes))
        for d in directions
    ]
    scored.sort(key=lambda pair: (-pair[1], pair[0].slug))
    return scored[:limit]
```

Всё, что ниже `matched_careers` (логика дедупликации/повторов в
существующем комментарии), не затрагивается — тот же принцип тай-брейка,
то же «не скрывать направления с точно совпадающим кодом», просто теперь
считаем баллы против небольшого набора правдоподобных кодов вместо одного.

### 2. `app/services/report_service.py` (около строк 760-770)

```python
codes = riasec_service.candidate_codes(profile_scores)
code = codes[0]  # без изменений: по-прежнему используется в AnalysisResult.code / meta / development_plan
meta = {
    "differentiation": riasec_service.differentiation(profile_scores),
    "consistency": riasec_service.consistency(code[:2]),
    "aversion": aversion_counts,
}
strengths, weaknesses = riasec_service.strengths_weaknesses(profile_scores, aversion_counts, counts)
plan = riasec_service.development_plan(code, weaknesses, aversion_counts, counts)

matched = await riasec_service.matched_careers(codes, db)
careers = [_career_dict(d, score) for d, score in matched]
```

Больше ничего в `build_report`, `report_v2_assembler.py`, `result_v2.py`
или `admin_result.py` не меняется — `careers` остаётся обычным
`list[dict]`, `AnalysisResult.code` по-прежнему хранит один трёхбуквенный
код (основной), а `build_riasec_careers` по-прежнему только нарезает и
подписывает уже готовый список.

### 3. Документация — `docs/senior-report-algorithm.md`

Добавить подраздел в §1.3 («Код студента»), описывающий `candidate_codes`
и порог близкого разрыва, и заметку в §2 (подбор профессий), что
`matched_careers` теперь считает баллы против каждого кандидата-кода и
сохраняет для каждого направления лучший результат. Использовать
обоснование из раздела «Контекст» выше — не просто описать механизм, но и
объяснить, почему произвольный тай-брейк не должен подаваться как
уверенный единственный ответ.

## Проверка

- `tests/unit/test_riasec_service.py`: существующий тест
  `test_top_code_breaks_ties_by_fixed_holland_order` должен остаться
  рабочим без изменений (сама `top_code` не меняется). Добавить: близкий
  разрыв на рангах 2-3 даёт оба порядка; близкий разрыв на рангах 1-2 даёт
  оба порядка; явный разрыв (например, существующий случай 53/47) даёт
  ровно один код; точное равенство тоже даёт оба порядка (это предельный
  случай близкого разрыва). Добавить тест `matched_careers` на реальных
  цифрах, воспроизведённых в этом разборе (R=43, I=52.9, A=47, S=79, E=46,
  C=53.1), на небольшом наборе фикстур `Direction`, фиксирующий, что
  объединённый список содержит направления, которые показал бы только
  порядок S-I-C, *и* направления, которые показал бы только S-C-I.
- `tests/integration/test_riasec_matched_careers.py`: расширить тестом на
  реальной БД для объединения (несколько кандидатов-кодов, проверка
  дедупликации/лучшего балла и того, что существующий тай-брейк по slug
  по-прежнему работает).
- `tests/integration/test_content_locale.py` (строки 140-144, тест
  `test_directions_kk_names_and_shared_slug`) — обернуть `code` в
  `[code]` под новую сигнатуру.
- Новый или расширенный интеграционный тест
  (`test_result_v2_fallback.py` или отдельный файл), прогоняющий профиль с
  реальным близким разрывом через `report_service.build_report`
  целиком end-to-end, подтверждающий, что возвращённый список `careers`
  больше не привязан к одному-единственному порядку букв.
- Вручную: воспроизвести точный сценарий из этого разбора (R=43, I=52.9,
  A=47, S=79, E=46, C=53.1) через реальный слой сервисов (как уже
  сделано вручную в рамках этого разбора) и убедиться, что объединённый
  список теперь включает и направления в духе SIR/ISE, и направления в
  духе CSI/CSE, а не только один вариант.
- Полный набор тестов: `docker compose exec api pytest`.

## Затрагиваемые файлы

- `app/services/riasec_service.py` — `_NEAR_TIE_THRESHOLD`, `_ranked_types`,
  `candidate_codes`, изменение сигнатуры `matched_careers`.
- `app/services/report_service.py` — ветка RIASEC в `build_report`
  (~строки 754-770).
- `docs/senior-report-algorithm.md` — §1.3 / §2.
- `tests/unit/test_riasec_service.py`,
  `tests/integration/test_riasec_matched_careers.py`,
  `tests/integration/test_content_locale.py` (строка 142/144 — обернуть
  `code` в `[code]`), плюс один новый/расширенный end-to-end
  интеграционный тест.

## Подтверждённое отсутствие побочных эффектов

- Снапшоты OpenAPI/ответов (`tests/snapshots/openapi_riasec_result_response.json`,
  `openapi_mi_result_response.json`) — `careers` остаётся
  `list[StudentCareer]`, схема не меняется, эти снапшоты перегенерировать
  не нужно.
- `report_v2_assembler.py`, `result_v2.py`, `admin_result.py` — не
  затрагиваются, подтверждено выше.
