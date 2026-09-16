"""
Seed script: populate the `questions` table with the 36 canonical
`boyko_empathy` items from boyko_empathy_bank.py (content-only — `channel`
and `keyed` live in the bank file for the future scoring service to resolve
via `Question.order`, not DB columns, same as elers_bank.py). PRO-338 Ф1.9,
pattern 1:1 with seed_elers_questions.py.

Run inside Docker, AFTER seed_elers_questions.py (shares the same `order`
numbering space, contiguous within the "Дополнительные тесты" sub-section
so the battery never interleaves it with RIASEC/BigFive/MI):
    docker-compose exec api python scripts/seed_boyko_empathy_questions.py

Idempotent, self-healing: upserts by `order`, deletes any DB row tagged
instrument='boyko_empathy' whose `order` is no longer in the bank — same
pattern as every other seed_*_questions.py script.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.profile import AgeGroup
from app.models.question import Question, QuestionInstrument
from app.services.admin_lock import has_overrides, sync_fields
from scripts.boyko_empathy_bank import QUESTIONS


async def main() -> None:
    async with async_session() as db:
        live_orders = {q["order"] for q in QUESTIONS}

        existing_result = await db.execute(
            select(Question).where(Question.instrument == QuestionInstrument.boyko_empathy)
        )
        existing_by_order = {q.order: q for q in existing_result.scalars().all()}

        inserted = updated = skipped = deleted = 0

        for data in QUESTIONS:
            age_tier = AgeGroup(data["age_tier"])
            existing = existing_by_order.get(data["order"])

            if existing is not None:
                changed = sync_fields(existing, {
                    "text": data["text"],
                    "age_tier": age_tier,
                })
                updated += 1 if changed else 0
                skipped += 0 if changed else 1
                continue

            db.add(Question(
                instrument=QuestionInstrument.boyko_empathy,
                text=data["text"],
                order=data["order"],
                age_tier=age_tier,
            ))
            inserted += 1

        for order, question in existing_by_order.items():
            if order not in live_orders and not has_overrides(question):
                await db.delete(question)
                deleted += 1

        await db.commit()
        print(
            f"Done. Inserted: {inserted}, updated: {updated}, "
            f"skipped (unchanged): {skipped}, orphans deleted: {deleted}"
        )
        print(f"Total boyko_empathy items in bank: {len(QUESTIONS)}")


if __name__ == "__main__":
    asyncio.run(main())
