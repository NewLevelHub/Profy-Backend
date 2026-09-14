"""
Seed script: populate the question_pairs table from question_pairing.py.
Run inside Docker, AFTER seed_riasec_questions.py, seed_bigfive_questions.py
and seed_mi_questions.py (pairs reference `questions` by `order`, resolved to
Question.id here):
docker-compose exec api python scripts/seed_question_pairs.py

Idempotent, self-healing: upserts by `(instrument, pair_index)`, deletes any
DB row whose key is no longer present in PAIRS. Admin-overridden text/rows
are preserved (admin_lock.sync_fields / has_overrides).

Localized (single-row redesign, docs/i18n-contract.md §8): one logical pair =
one row, `frame`/`option_a_text`/`option_b_text` stored whole as their bank
`{locale: str}` maps (icons are shared, not localized).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.profile import AgeGroup
from app.models.question import Question, QuestionInstrument
from app.models.question_pair import LOCALIZED_FIELDS, QuestionPair
from app.services.admin_lock import has_overrides, sync_fields
from scripts.question_pairing import PAIRS


async def main() -> None:
    async with async_session() as db:
        inserted = updated = skipped = deleted = 0

        order_to_id = dict((await db.execute(select(Question.order, Question.id))).all())

        live_keys = {(QuestionInstrument(p["instrument"]), p["pair_index"]) for p in PAIRS}

        existing_result = await db.execute(select(QuestionPair))
        existing_by_key = {
            (p.instrument, p.pair_index): p for p in existing_result.scalars().all()
        }

        for data in PAIRS:
            instrument = QuestionInstrument(data["instrument"])
            age_tier = AgeGroup(data["age_tier"])
            question_a_id = order_to_id[data["question_a_order"]]
            question_b_id = order_to_id[data["question_b_order"]]

            existing = existing_by_key.get((instrument, data["pair_index"]))
            if existing is not None:
                changed = False
                # Structural refs are never admin-overridable — sync directly.
                for attr, value in (
                    ("age_tier", age_tier),
                    ("question_a_id", question_a_id),
                    ("question_b_id", question_b_id),
                ):
                    if getattr(existing, attr) != value:
                        setattr(existing, attr, value)
                        changed = True
                # Displayed text/icons respect admin overrides.
                if sync_fields(
                    existing,
                    {
                        "frame": data["frame"],
                        "option_a_text": data.get("option_a_text"),
                        "option_b_text": data.get("option_b_text"),
                        "option_a_icon": data.get("option_a_icon"),
                        "option_b_icon": data.get("option_b_icon"),
                    },
                    localized_fields=LOCALIZED_FIELDS,
                ):
                    changed = True
                updated += changed
                skipped += not changed
                continue

            db.add(QuestionPair(
                instrument=instrument,
                age_tier=age_tier,
                pair_index=data["pair_index"],
                question_a_id=question_a_id,
                question_b_id=question_b_id,
                frame=data["frame"],
                option_a_text=data.get("option_a_text"),
                option_b_text=data.get("option_b_text"),
                option_a_icon=data.get("option_a_icon"),
                option_b_icon=data.get("option_b_icon"),
            ))
            inserted += 1

        for key, pair in existing_by_key.items():
            if key not in live_keys and not has_overrides(pair):
                await db.delete(pair)
                deleted += 1

        await db.commit()
        print(
            f"Done. Inserted: {inserted}, updated: {updated}, "
            f"skipped (unchanged): {skipped}, orphans deleted: {deleted}"
        )
        print(f"Bank: {len(PAIRS)} logical pairs")


if __name__ == "__main__":
    asyncio.run(main())
