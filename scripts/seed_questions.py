"""
Seed script: populate the questions table from methodology question bank.
Run inside Docker: docker-compose exec api python scripts/seed_questions.py
Idempotent: upserts by (block, age_group, order).
"""
import asyncio
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.question import Question
from scripts.question_bank import QUESTIONS


def _to_db_options(question: dict[str, Any]) -> Any:
    if question.get("type") == "likert":
        return {
            "type": "likert",
            "weights": question["weights"],
            "reversed": question.get("reversed", False),
        }
    return question["options"]


async def main() -> None:
    async with async_session() as db:
        inserted = 0
        updated = 0
        skipped = 0

        for q in QUESTIONS:
            result = await db.execute(
                select(Question).where(
                    Question.block == q["block"],
                    Question.age_group == q["age_group"],
                    Question.order == q["order"],
                )
            )
            existing = result.scalar_one_or_none()
            options = _to_db_options(q)

            if existing is not None:
                if existing.text != q["text"] or existing.options != options:
                    existing.text = q["text"]
                    existing.options = options
                    updated += 1
                else:
                    skipped += 1
                continue

            db.add(Question(
                block=q["block"],
                age_group=q["age_group"],
                text=q["text"],
                options=options,
                order=q["order"],
            ))
            inserted += 1

        await db.commit()
        print(
            f"Done. Inserted: {inserted}, updated: {updated}, "
            f"skipped (unchanged): {skipped}"
        )
        print(f"Total questions in bank: {len(QUESTIONS)}")


if __name__ == "__main__":
    asyncio.run(main())
