"""
Seed script: populate the question_pairs table from question_pairing.py.
Run inside Docker, AFTER seed_riasec_questions.py and seed_bigfive_questions.py
(pairs reference those rows by `order`, resolved to Question.id here):
docker-compose exec api python scripts/seed_question_pairs.py

Idempotent, self-healing: upserts by `(instrument, pair_index)`, deletes any
DB row whose `(instrument, pair_index)` is no longer present in PAIRS — same
pattern as the other seed scripts.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.profile import AgeGroup
from app.models.question import Question, QuestionInstrument
from app.models.question_pair import QuestionPair
from scripts.question_pairing import PAIRS


async def main() -> None:
    async with async_session() as db:
        order_to_id_result = await db.execute(select(Question.order, Question.id))
        order_to_id = dict(order_to_id_result.all())

        existing_result = await db.execute(select(QuestionPair))
        existing_by_key = {(p.instrument, p.pair_index): p for p in existing_result.scalars().all()}

        live_keys = {(QuestionInstrument(p["instrument"]), p["pair_index"]) for p in PAIRS}

        inserted = 0
        updated = 0
        skipped = 0
        deleted = 0

        for data in PAIRS:
            instrument = QuestionInstrument(data["instrument"])
            age_tier = AgeGroup(data["age_tier"])
            key = (instrument, data["pair_index"])
            question_a_id = order_to_id[data["question_a_order"]]
            question_b_id = order_to_id[data["question_b_order"]]
            existing = existing_by_key.get(key)

            if existing is not None:
                changed = False
                if existing.age_tier != age_tier:
                    existing.age_tier = age_tier
                    changed = True
                if existing.question_a_id != question_a_id:
                    existing.question_a_id = question_a_id
                    changed = True
                if existing.question_b_id != question_b_id:
                    existing.question_b_id = question_b_id
                    changed = True
                if existing.frame != data["frame"]:
                    existing.frame = data["frame"]
                    changed = True
                if changed:
                    updated += 1
                else:
                    skipped += 1
                continue

            db.add(QuestionPair(
                instrument=instrument,
                age_tier=age_tier,
                pair_index=data["pair_index"],
                question_a_id=question_a_id,
                question_b_id=question_b_id,
                frame=data["frame"],
            ))
            inserted += 1

        for key, pair in existing_by_key.items():
            if key not in live_keys:
                await db.delete(pair)
                deleted += 1

        await db.commit()
        print(
            f"Done. Inserted: {inserted}, updated: {updated}, "
            f"skipped (unchanged): {skipped}, orphans deleted: {deleted}"
        )
        print(f"Total pairs in bank: {len(PAIRS)}")


if __name__ == "__main__":
    asyncio.run(main())
