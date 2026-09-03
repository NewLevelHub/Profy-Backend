# Замена университетского блока в `cd.yml` / `cd-dev.yml`

## Суть

Пайплайн наполнения `universities` / `programs` заменён на **один закоммиченный
файл** `profi-backend/scripts/data/university_snapshot.clean.json` и **один
загрузчик** `scripts/build_universities.py`. В `start.sh` (локальный запуск)
замена уже сделана и протестирована. То же нужно сделать в обоих CD-workflow,
иначе деплой продолжит гонять старые ~23 скрипта и пересоздаст данные с
дублями поверх/вместо консолидированных.

Психометрический блок (`seed_riasec_questions` … `apply_direction_content`)
**не меняется** — `build_universities.py` требует уже засеянных `directions`
(теги профессий резолвятся по `Direction.slug`), поэтому его строка идёт
сразу после `apply_direction_content.py`.

---

## `cd.yml` (prod)

**Оставить** строки 172–179 (от `seed_riasec_questions.py` до
`apply_direction_content.py`).

**Удалить** строки **180–202** — 23 университетских скрипта:
`seed_kz_universities.py`, `seed_92_professions_universities.py`,
`backfill_program_cost_label_2027.py`, `apply_uniranks_kz_2027.py`,
`apply_uniranks_not_ranked.py`, `apply_university_enrichment_2027.py`,
`apply_program_requirements_content_2027.py`,
`apply_grant_admission_data_2026.py`,
`backfill_program_source_metadata_2026.py`, `apply_ovpo_codes.py`,
`merge_duplicate_programs.py`, `backfill_world_ranking.py`,
`backfill_cost_range.py`, `backfill_ranking_from_label.py`,
`backfill_kz_program_description.py`,
`backfill_kazatu_duplicate_group_labels.py`,
`apply_specialty_names_from_review.py`, `fix_enu_kazatu_program_names.py`,
`backfill_strip_masters_domestic_cost.py`,
`apply_university_descriptions_batch1.py`,
`backfill_foreign_cost_numeric.py`, `backfill_foreign_cost_numeric_pass2.py`,
`apply_ent_profile_subjects.py`.

**Вставить на их место одну строку:**

```yaml
            docker compose --env-file .env.production -f docker-compose.prod.yml exec -T api python scripts/build_universities.py
```

Результат — блок «Running seed scripts…» заканчивается так:

```yaml
            docker compose --env-file .env.production -f docker-compose.prod.yml exec -T api python scripts/seed_riasec_directions.py
            docker compose --env-file .env.production -f docker-compose.prod.yml exec -T api python scripts/apply_direction_content.py
            docker compose --env-file .env.production -f docker-compose.prod.yml exec -T api python scripts/build_universities.py

            echo "=== Production deploy complete ==="
```

---

## `cd-dev.yml` (dev)

Ровно то же, другой префикс команды (`.env.development -f docker-compose.dev.yml -p profy-dev exec -T api_dev`).

**Оставить** строки 185–192 (до `apply_direction_content.py`).
**Удалить** строки **193–215** (те же 23 скрипта).
**Вставить:**

```yaml
            docker compose --env-file .env.development -f docker-compose.dev.yml -p profy-dev exec -T api_dev python scripts/build_universities.py
```

---

## Предусловия (уже выполнены, проверить не мешает)

- `university_snapshot.clean.json` (~24 МБ) лежит в `scripts/data/` и попадает
  в образ: `Dockerfile` делает `COPY . .`, `.dockerignore` его не исключает.
- `scripts/data/program_direction_map.json`, `slug_rename_map.json`,
  `photo_alias_map.json` — build-time артефакты, загрузчику НЕ нужны (теги и
  всё остальное уже впечатаны в `.clean.json`).
- `directions` засеяны раньше в том же блоке — порядок сохранён.

---

## Что делает первый прогон на каждом окружении

- **Разовый destructive-пересбор:** удаляет все строки `universities` /
  `programs` / `university_external_refs` со старыми случайными `uuid4()` и
  вставляет заново с детерминированными `uuid5`. На следующих деплоях —
  near-noop (`insert=0 update=0 prune=0`).
- `direction_roadmaps.program_id` (`ON DELETE SET NULL`) обнуляется у
  студентов, сохранявших план под конкретную программу — **только на этом
  первом прогоне**; дальше id стабильны.
- `university_images` (staging для `export_university_photos.py`) —
  cascade-удаляется. Раздачу фото это не трогает (nginx отдаёт из папки по
  slug), но пересобрать папку через `export_university_photos.py` без
  переимпорта фото после этого нельзя.

---

## Разовый ручной шаг на медиахостах

CD фото не трогает. Канонизация slug переименовала ~220 вузов, поэтому на
каждом хосте с папкой фото (dev, prod) один раз:

```bash
cd <repo>/profi-backend
python scripts/rename_university_photos.py --media-dir /srv/profy-media --apply
```

Идемпотентно (повторный запуск — no-op). Скрипт чистый stdlib, БД не трогает,
берёт `scripts/data/slug_rename_map.json` + `photo_alias_map.json`.

---

## Порядок раскатки

1. Правка в `cd-dev.yml` → пуш в `dev` → проверить `dev.profy.newlevelhub.kz`
   (страница вузов, страница профессии, roadmap с выбором программы), прогнать
   `rename_university_photos.py --apply` на dev-медиахосте.
2. Пожить на dev.
3. Правка в `cd.yml` → мердж `dev → main` → то же на проде.

---

## Проверка после деплоя

В логах шага «Running seed scripts…» ожидать от `build_universities.py`:

```
universities   insert=<N>  update=0  prune=<M>
programs       insert=<N>  update=0  prune=<M>
profession tag links: ~19000   programs with no tag: 0
```

(на первом прогоне `insert` ≈ 2400 вузов / 12400 программ, `prune` ≈ размер
старого набора; на последующих — всё по нулям).

Опционально — ассерт отдельным шагом (exit 1, если БД ≠ снапшот):

```bash
docker compose ... exec -T api python scripts/build_universities.py --check
```

---

## Откат

Загрузчик читает только `.clean.json`, поэтому «откат кода» = вернуть старый
блок скриптов в workflow. Но данные после первого прогона уже с
детерминированными id; старые скрипты, запущенные поверх, создадут дубли
(их прежняя проблема). Практический откат — `git revert` PR целиком
(workflow + `build_universities.py` + `.clean.json`) и один прогон старого
блока на чистой БД.
