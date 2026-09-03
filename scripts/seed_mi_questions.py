"""
Seed script: populate the questions table (MI rows) from mi_question_bank.py.
Run inside Docker, AFTER seed_riasec_questions.py and seed_bigfive_questions.py
(order continues from their combined bank length):
docker-compose exec api python scripts/seed_mi_questions.py

Idempotent, self-healing: upserts by `(order, locale)`, deletes any mi DB row
whose `(order, locale)` is no longer present in QUESTIONS — same pattern as
seed_riasec_questions.py/seed_bigfive_questions.py. Only touches
instrument='mi', `locale='ru'` rows (the bank is Russian-only; KZ-301).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.profile import AgeGroup
from app.models.question import MIType, Question, QuestionInstrument
from scripts.mi_question_bank import QUESTIONS

# mi_question_bank.py holds Russian text only.
BANK_LOCALE = "ru"


async def main() -> None:
    async with async_session() as db:
        live_orders = {q["order"] for q in QUESTIONS}

        existing_result = await db.execute(
            select(Question).where(
                Question.instrument == QuestionInstrument.mi,
                Question.locale == BANK_LOCALE,
            )
        )
        existing_by_order = {q.order: q for q in existing_result.scalars().all()}

        inserted = 0
        updated = 0
        skipped = 0
        deleted = 0

        for data in QUESTIONS:
            existing = existing_by_order.get(data["order"])
            category = MIType(data["mi_category"])
            age_tier = AgeGroup(data["age_tier"])

            if existing is not None:
                changed = False
                if existing.mi_category != category:
                    existing.mi_category = category
                    changed = True
                if existing.text != data["text"]:
                    existing.text = data["text"]
                    changed = True
                if existing.age_tier != age_tier:
                    existing.age_tier = age_tier
                    changed = True
                if existing.short_text != data.get("short_text"):
                    existing.short_text = data.get("short_text")
                    changed = True
                if existing.icon != data.get("icon"):
                    existing.icon = data.get("icon")
                    changed = True
                if changed:
                    updated += 1
                else:
                    skipped += 1
                continue

            db.add(
                Question(
                    instrument=QuestionInstrument.mi,
                    mi_category=category,
                    text=data["text"],
                    order=data["order"],
                    age_tier=age_tier,
                    short_text=data.get("short_text"),
                    icon=data.get("icon"),
                    locale=BANK_LOCALE,
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
