"""One-off content-generation script for the `directions` table.

Context: all 92 rows in `directions` (seeded by scripts/seed_riasec_directions.py
from the RIASEC-migration profession catalog) have description/skills_needed/
subjects_to_develop/first_steps empty by design (see app/models/direction.py
docstring) — that content was explicitly deferred to a separate backlog item
(Рефакторинг.md Scope section). This script drafts that content via LLM so a
human can review it before it reaches students (result-quality-fixes.md §4,
"LLM-генерация + моя проверка" — the user's chosen approach, not automatic).

This does NOT write to the database. It writes a review file
(direction_content_review.json, this directory) for a human to read and
approve/edit. Applying the reviewed file to the DB is a separate script
(scripts/apply_direction_content.py) run only after that review.

Run inside Docker: docker compose exec api python scripts/generate_direction_content.py
"""
import asyncio
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.direction import Direction
from app.services import llm_client

OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "direction_content_review.json")

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["description", "skills_needed", "subjects_to_develop", "first_steps"],
    "properties": {
        "description": {"type": "string"},
        "skills_needed": {"type": "array", "items": {"type": "string"}},
        "subjects_to_develop": {"type": "array", "items": {"type": "string"}},
        "first_steps": {"type": "array", "items": {"type": "string"}},
    },
}

_SYSTEM_PROMPT = """\
Ты наполняешь справочник профессий для профориентационного приложения для \
школьников 10-18 лет (Казахстан/СНГ). Пиши по-русски, просто и конкретно, \
без канцелярита и без воды.

ЗАПРЕЩЕНО:
- Придумывать названия конкретных вузов, курсов, сертификатов, платформ или \
ссылок — их либо нет в этом справочнике, либо они берутся из отдельного, \
проверенного каталога, не из твоего текста.
- Указывать зарплаты, проценты трудоустройства, конкурс на место или любые \
другие цифры/статистику — они быстро устаревают и создают ложные ожидания.
- Оценочные или пугающие формулировки ("эта профессия исчезнет", "туда \
сложно поступить", "нужен только талант").

Структура ответа (строго по схеме):
- description: 2-3 предложения простым языком — чем конкретно занимается \
человек в этой роли день за днём. Не общие слова уровня "интересная \
профессия", а конкретика: что делает, с чем работает, для кого/чего.
- skills_needed: 4-6 конкретных навыков, реально нужных именно в этой \
профессии (не абстрактные "коммуникабельность" без контекста, а например \
"объяснять сложные вещи простыми словами" для преподавателя).
- subjects_to_develop: 2-4 обычных школьных предмета (математика, физика, \
информатика, биология, химия, история, обществознание, русский/казахский \
язык, литература, иностранный язык, ИЗО, черчение и т.п. — только реальные \
школьные предметы), которые реально пригодятся в этом направлении.
- first_steps: ровно 3 маленьких конкретных действия, которые школьник \
может попробовать САМ уже сейчас, чтобы приблизиться к этой сфере — \
мини-проект, наблюдение, самостоятельная попытка сделать что-то простое \
в этой области. Не "погугли", не "посмотри видео про X" (это не \
верифицируемо и быстро устареет), а что-то деятельное и конкретное.
"""


def _user_prompt(direction: Direction) -> str:
    return (
        f"Профессия: {direction.name}\n"
        f"Условный код интересов (RIASEC): {direction.holland_code}\n\n"
        "Заполни описание по инструкции выше."
    )


_DIGIT_RE = re.compile(r"\d")


def _quality_flags(payload: dict) -> list[str]:
    """Cheap automated red flags for the human reviewer to look at first —
    not a hard gate, this script never auto-rejects (a human reviews the
    whole file regardless)."""
    flags = []
    if _DIGIT_RE.search(payload["description"]):
        flags.append("description contains a digit")
    if not (40 <= len(payload["description"]) <= 500):
        flags.append(f"description length {len(payload['description'])} looks off")
    if len(payload["first_steps"]) != 3:
        flags.append(f"first_steps has {len(payload['first_steps'])} items, expected 3")
    if not (4 <= len(payload["skills_needed"]) <= 6):
        flags.append(f"skills_needed has {len(payload['skills_needed'])} items, expected 4-6")
    if not (2 <= len(payload["subjects_to_develop"]) <= 4):
        flags.append(f"subjects_to_develop has {len(payload['subjects_to_develop'])} items, expected 2-4")
    return flags


async def _generate_one(direction: Direction) -> dict:
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _user_prompt(direction)},
    ]
    payload = await llm_client.complete_json(messages, _SCHEMA, "direction_content")
    return payload


async def main() -> None:
    if not llm_client.is_enabled():
        print("LLM disabled — nothing to generate.")
        return

    async with async_session() as db:
        result = await db.execute(select(Direction).order_by(Direction.slug))
        directions = list(result.scalars().all())

    print(f"Generating content for {len(directions)} directions...")
    results: list[dict] = []
    failures: list[str] = []

    for i, direction in enumerate(directions, start=1):
        try:
            payload = await _generate_one(direction)
        except llm_client.LLMError as exc:
            print(f"  [{i}/{len(directions)}] FAILED {direction.slug}: {type(exc).__name__}")
            failures.append(direction.slug)
            continue

        flags = _quality_flags(payload)
        flag_note = f" ⚠ {'; '.join(flags)}" if flags else ""
        print(f"  [{i}/{len(directions)}] OK {direction.slug}{flag_note}")

        results.append({
            "slug": direction.slug,
            "name": direction.name,
            "holland_code": direction.holland_code,
            "flags": flags,
            **payload,
        })

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    flagged_count = sum(1 for r in results if r["flags"])
    print(f"\nDone. {len(results)} generated, {len(failures)} failed, {flagged_count} flagged for review.")
    print(f"Written to {OUTPUT_PATH}")
    if failures:
        print(f"Failed slugs (not in output, rerun script to retry — it's not idempotent-skip, will regenerate all): {failures}")


if __name__ == "__main__":
    asyncio.run(main())
