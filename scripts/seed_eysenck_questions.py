"""
Seed script: populate the `questions` table with the 57 `eysenck` items
from eysenck_bank.py (content-only — `scale`/`keyed` live in the bank file
for Ф1.5's future scoring service to resolve via `Question.order`, not a
DB column, same as professional_types_service.py). PRO-338 Ф0.8/Ф1.4,
pattern 1:1 with seed_lie_scale_questions.py (PRO-298).

Run inside Docker, AFTER seed_professional_types_questions.py (shares the
same `order` numbering space, contiguous within the "Дополнительные тесты"
sub-section so the battery never interleaves it with RIASEC/BigFive/MI):
    docker-compose exec api python scripts/seed_eysenck_questions.py

Idempotent, self-healing: upserts by `order`, deletes any DB row tagged
instrument='eysenck' whose `order` is no longer in the bank — same pattern
as every other seed_*_questions.py script.
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
from scripts.eysenck_bank import QUESTIONS


async def main() -> None:
    async with async_session() as db:
        live_orders = {q["order"] for q in QUESTIONS}

        existing_result = await db.execute(
            select(Question).where(Question.instrument == QuestionInstrument.eysenck)
        )
        existing_by_order = {q.order: q for q in existing_result.scalars().all()}

        inserted = updated = skipped = deleted = 0

        for data in QUESTIONS:
            age_tier = AgeGroup(data["age_tier"])
            # `Question.text` is `{locale: str}` JSONB (docs/i18n-contract.md
            # §8) — this bank predates that migration and still carries plain
            # `ru` strings. No `kk` translation exists yet for this
            # specialist-only content; `pick_locale()` falls back to `ru`
            # when `kk` is missing, so `{"ru": ...}` alone is correct today.
            text = {"ru": data["text"]}
            existing = existing_by_order.get(data["order"])

            if existing is not None:
                changed = sync_fields(existing, {
                    "text": text,
                    "age_tier": age_tier,
                })
                updated += 1 if changed else 0
                skipped += 0 if changed else 1
                continue

            db.add(Question(
                instrument=QuestionInstrument.eysenck,
                text=text,
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
        print(f"Total eysenck items in bank: {len(QUESTIONS)}")


if __name__ == "__main__":
    asyncio.run(main())
