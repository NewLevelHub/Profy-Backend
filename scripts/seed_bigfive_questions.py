"""
Seed script: populate the questions table (Big Five rows) from
bigfive_question_bank.py.
Run inside Docker, AFTER seed_riasec_questions.py (order continues from the
RIASEC bank's length): docker-compose exec api python scripts/seed_bigfive_questions.py

Idempotent, self-healing: upserts by `order`, deletes any big_five DB row
whose `order` is no longer present in QUESTIONS — same pattern as
seed_riasec_questions.py. Only touches instrument='big_five' rows.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.question import BigFiveDomain, Keyed, Question, QuestionInstrument
from scripts.bigfive_question_bank import QUESTIONS


async def main() -> None:
    async with async_session() as db:
        live_orders = {q["order"] for q in QUESTIONS}

        existing_result = await db.execute(
            select(Question).where(Question.instrument == QuestionInstrument.big_five)
        )
        existing_by_order = {q.order: q for q in existing_result.scalars().all()}

        inserted = 0
        updated = 0
        skipped = 0
        deleted = 0

        for data in QUESTIONS:
            existing = existing_by_order.get(data["order"])
            domain = BigFiveDomain(data["bigfive_domain"])
            keyed = Keyed(data["keyed"])

            if existing is not None:
                changed = False
                if existing.bigfive_domain != domain:
                    existing.bigfive_domain = domain
                    changed = True
                if existing.facet != data["facet"]:
                    existing.facet = data["facet"]
                    changed = True
                if existing.keyed != keyed:
                    existing.keyed = keyed
                    changed = True
                if existing.text != data["text"]:
                    existing.text = data["text"]
                    changed = True
                if changed:
                    updated += 1
                else:
                    skipped += 1
                continue

            db.add(
                Question(
                    instrument=QuestionInstrument.big_five,
                    bigfive_domain=domain,
                    facet=data["facet"],
                    keyed=keyed,
                    text=data["text"],
                    order=data["order"],
                )
            )
            inserted += 1

        for order, question in existing_by_order.items():
            if order not in live_orders:
                await db.delete(question)
                deleted += 1

        await db.commit()
        print(
            f"Done. Inserted: {inserted}, updated: {updated}, "
            f"skipped (unchanged): {skipped}, orphans deleted: {deleted}"
        )
        print(f"Total questions in bank: {len(QUESTIONS)}")


if __name__ == "__main__":
    asyncio.run(main())
