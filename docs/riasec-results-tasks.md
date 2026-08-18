# Адаптация `/result` под RIASEC/MI — актуальный список задач

Обновлено: 2026-08-07 после merge `origin/New-Test-Logic`.

Этот файл был создан до hard cutover и раньше считал решение
«replace/coexist» открытым. Это больше не так:

- миграция `0024_riasec_migration.py` физически удалила старый
  24-осевой движок;
- middle/senior используют RIASEC;
- junior использует MI вместо RIASEC;
- junior/middle отвечают Harter motivation pairs, senior — triplets;
- публичные маршруты — `POST /api/v1/result/generate` и
  `GET /api/v1/result/{assessment_id}`.

Источник истины для следующего рефактора:
`docs/result-report-redesign-plan.md` и
`docs/frontend-result-api-contract.md`.

Легенда:

- ✅ реализовано в текущем raw report pipeline;
- 🟢 готово к реализации в student v2;
- 🟡 реализовано частично, требуется регрессия/доводка;
- ⛔ устарело или отменено новым архитектурным решением.

## Старые задачи — актуальный статус

| # | Задача | Статус | Актуальный комментарий |
|---|---|---|---|
| 21 | Подсчёт RIASEC-профиля | ✅ | `riasec_service.raw_scores/normalize/top_code`, ветка middle/senior в `report_service.build_report` |
| 22 | `meta`: differentiation / consistency / aversion | ✅ | Реализовано и для RIASEC, и для MI; raw schema должна получить нейтральное имя вместо `RiasecMeta` |
| 23 | Сильные/слабые стороны RIASEC | ✅ | `riasec_service.strengths_weaknesses`; для junior отдельная MI-реализация |
| 24 | Career ranking по Holland match | ✅ | `riasec_service.matched_careers`; применяется только middle/senior |
| 25 | `match_percent/questions_answered` в student API | ⛔ | Raw counts не входят в целевой student v2; нужные метрики остаются admin-only |
| 26 | Подтверждение направления | ⛔ | Вынесено из result scope; текущее поведение direction roadmap описано в frontend roadmap contract |
| 27 | Старый `is_direction_specific` fallback | ⛔ | Старый движок удалён, задача больше не существует |
| 28 | Переписать старую Akinator result schema | ✅ | Текущий `AnalysisResultResponse` уже RIASEC/MI raw; следующий шаг — разделить student/admin schemas |
| 29 | Тесты результата | 🟡 | Базовый pipeline существует, но нет полной MI/Harter age matrix и v2 contract coverage |
| 30 | Frontend contract | 🟡 | Целевой v2 зафиксирован в `docs/frontend-result-api-contract.md`, OpenAPI/реализация ещё не обновлены |
| 36 | Совместимость со старыми akinator assessments | ⛔ | Миграция `0024` сделала hard cutover с очисткой старых данных; dual-read не реализуется |

## Новые задачи после MI/Harter merge

| # | Задача | Статус | Критерий готовности |
|---|---|---|---|
| 37 | Разделить raw admin и student v2 schemas | 🟢 | Student не содержит raw scores; admin сохраняет полный `AnalysisResult` |
| 38 | Сделать interest block discriminated union | 🟢 | `interest_instrument=mi` → 8 MI-сфер; `riasec` → 6 сфер; фронт не угадывает тип по ключам |
| 39 | Сохранить полезный junior output без careers | 🟢 | MI response имеет `careers=[]` и `exploration_activities` из `mi_content`, без выдуманного Holland matching |
| 40 | Унифицировать narrative evidence | 🟢 | MI/RIASEC, Big Five и оба motivation flow дают только разрешённые categorical refs, без raw numbers |
| 41 | Закрыть completion gate | 🟢 | Junior/middle проверяют motivation pairs, senior triplets; junior Likert total не считает retired RIASEC |
| 42 | Закрыть retake/cache invalidation | 🟢 | `assessment`, question pairs, motivation pairs и triplets удаляют v2 cache, report и оба roadmap flow |
| 43 | Age-matrix regression suite | 🟢 | Junior MI+Harter, middle RIASEC+Harter, senior RIASEC+triplets + schema snapshots |
| 44 | Перевести migration plan на текущую head | 🟢 | Не переиспользовать `0034–0040`; новая result migration создаётся от фактической Alembic head |

## Что не меняет student contract

Harter pairs используют другие таблицы и scoring, но в
`report_service.build_report` сводятся к тем же `motivation_top` и
`motivation_highlights`, что senior triplets. Поэтому отдельный
`motivation_pair_highlights` в response не нужен. Нужны только отдельные
completion, invalidation и test paths.
