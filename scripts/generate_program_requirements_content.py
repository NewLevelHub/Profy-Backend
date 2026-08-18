"""One-off content-generation script for the 92-professions batch
(scripts/seed_92_professions_universities.py), whose admission requirements
live only as free-text prose in Program.requirements["notes"] (see
scripts/backfill_program_cost_label_2027.py) — exams/portfolio/documents/
deadline never reached the structured fields university_requirements.py
reads, so the requirements card renders mostly "—" for these programs even
when the text plainly states, e.g., "обязательная сдача сложных вступительных
экзаменов по биологии, химии и медицинскому английскому."

This script drafts that structured extraction via LLM so a human can review
it before it reaches students (same approach as generate_direction_content.py
— "LLM-генерация + моя проверка"). It does NOT write to the database. It
writes a review file (program_requirements_review_2027.json, this directory)
for a human to read and approve/edit. Applying the reviewed file to the DB is
a separate script (apply_program_requirements_content_2027.py) run only after
that review.

Grouped by (university_id, notes text) — the same requirements text is
shared across every direction in a cluster for a given university, so ~920
programs collapse to ~130 unique LLM calls.

Run inside Docker: docker compose exec api python scripts/generate_program_requirements_content.py
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.program import Program
from app.models.university import University
from app.services import llm_client

OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "program_requirements_review_2027.json")

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["exams", "needs_portfolio", "needs_essay", "needs_recommendations", "needs_interview", "application_deadline"],
    "properties": {
        "exams": {"type": "array", "items": {"type": "string"}},
        "needs_portfolio": {"type": ["boolean", "null"]},
        "needs_essay": {"type": ["boolean", "null"]},
        "needs_recommendations": {"type": ["boolean", "null"]},
        "needs_interview": {"type": ["boolean", "null"]},
        "application_deadline": {"type": ["string", "null"]},
    },
}

_SYSTEM_PROMPT = """\
Ты извлекаешь структурированные факты из текста о требованиях поступления в \
университет для профориентационного приложения. Текст — свободная проза на \
русском, написанная человеком, не по шаблону.

СТРОГОЕ ПРАВИЛО: доставай только то, что явно написано в тексте. Никогда не \
угадывай и не достраивай по общим знаниям о том, что "обычно нужно" для \
такого вуза или специальности.

- exams: список конкретных предметов/экзаменов, если они явно названы \
(например ["Биология", "Химия"]). Общие фразы вроде "вступительные экзамены" \
без названных предметов — не считается, оставь пустой список.
- needs_portfolio / needs_essay / needs_recommendations / needs_interview: \
true — если явно упомянуто требование; false — ТОЛЬКО если текст явно говорит, \
что это не требуется; null — если текст вообще не упоминает это (это самый \
частый случай, не путай его с false).
  needs_essay = true также при любой формулировке "мотивационное письмо", \
"мотивационное эссе", "эссе о мотивации", "letter of motivation", "personal \
statement", "cover letter" — это одно и то же поле в системе, не только \
буквальное слово "эссе".
- application_deadline: дедлайн подачи, если явно назван (дата или период). \
Иначе null.

Отвечай строго по схеме, без пояснений."""


def _user_prompt(university_name: str, sample_program_name: str, notes_text: str) -> str:
    return (
        f"Университет: {university_name}\n"
        f"Пример направления в этом кластере: {sample_program_name}\n"
        f"Текст о требованиях поступления:\n{notes_text}\n\n"
        "Извлеки структурированные факты по инструкции выше."
    )


async def _generate_one(university_name: str, sample_program_name: str, notes_text: str) -> dict:
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _user_prompt(university_name, sample_program_name, notes_text)},
    ]
    return await llm_client.complete_json(messages, _SCHEMA, "program_requirements")


async def main() -> None:
    if not llm_client.is_enabled():
        print("LLM disabled — nothing to generate.")
        return

    async with async_session() as db:
        result = await db.execute(
            select(Program, University)
            .join(University, Program.university_id == University.id)
            .where(Program.cost_label.isnot(None))
            .order_by(University.name, Program.name)
        )
        rows = result.all()

    # Group by (university_id, notes text) — same text repeats across every
    # direction in a cluster for a given university.
    groups: dict[tuple, dict] = {}
    for program, university in rows:
        notes = program.requirements.get("notes") or []
        notes_text = notes[0] if notes else ""
        key = (str(university.id), notes_text)
        if key not in groups:
            groups[key] = {
                "university_id": str(university.id),
                "university_slug": university.slug,
                "university_name": university.name,
                "sample_program_name": program.name,
                "notes_text": notes_text,
                "program_ids": [],
            }
        groups[key]["program_ids"].append(str(program.id))

    group_list = list(groups.values())
    print(f"Generating content for {len(group_list)} unique (university, requirements-text) groups "
          f"covering {sum(len(g['program_ids']) for g in group_list)} programs...")

    results: list[dict] = []
    failures: list[str] = []

    for i, group in enumerate(group_list, start=1):
        if not group["notes_text"]:
            continue
        try:
            payload = await _generate_one(
                group["university_name"], group["sample_program_name"], group["notes_text"]
            )
        except llm_client.LLMError as exc:
            print(f"  [{i}/{len(group_list)}] FAILED {group['university_slug']}: {type(exc).__name__}")
            failures.append(group["university_slug"])
            continue

        print(f"  [{i}/{len(group_list)}] OK {group['university_slug']} ({len(group['program_ids'])} programs)")
        results.append({
            "university_slug": group["university_slug"],
            "university_name": group["university_name"],
            "program_ids": group["program_ids"],
            "notes_text": group["notes_text"],
            **payload,
        })

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nDone. {len(results)} groups generated, {len(failures)} failed.")
    print(f"Written to {OUTPUT_PATH}")
    if failures:
        print(f"Failed slugs (rerun script to retry — not idempotent-skip, regenerates all): {failures}")


if __name__ == "__main__":
    asyncio.run(main())
