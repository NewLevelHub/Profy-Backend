"""
Seed script: populate the question_pairs table from question_pairing.py.
Run inside Docker, AFTER seed_riasec_questions.py, seed_bigfive_questions.py
and seed_mi_questions.py (pairs reference `questions` by `order`, resolved to
Question.id here — per locale):
docker-compose exec api python scripts/seed_question_pairs.py

Idempotent, self-healing: upserts by `(instrument, pair_index, locale)`,
deletes any DB row whose `(instrument, pair_index, locale)` is no longer present
in PAIRS *for that locale* — same pattern as the other seed scripts.
Admin-overridden text/rows are preserved (admin_lock.sync_fields / has_overrides).

Localized (KZ-301/KZ-304): each pair's `frame` / `option_a_text` /
`option_b_text` is `{locale: str}` (icons shared); `PAIR_LOCALES` lists the
bank's locales. One logical pair = one row per locale, keyed
`(instrument, pair_index, locale)`, referencing that locale's question rows.
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
from app.services.admin_lock import has_overrides, sync_fields
from scripts.question_pairing import PAIR_LOCALES, PAIRS


def _text(field, locale: str):
    """A bilingual `{locale: str}` content field -> its value for `locale`
    (None if the pair has no text there, which no live pair does)."""
    if field is None:
        return None
    return field.get(locale)


async def main() -> None:
    async with async_session() as db:
        inserted = updated = skipped = deleted = 0

        for locale in PAIR_LOCALES:
            order_to_id = dict(
                (
                    await db.execute(
                        select(Question.order, Question.id).where(Question.locale == locale)
                    )
                ).all()
            )

            live = [p for p in PAIRS if locale in (p["frame"] or {})]
            live_keys = {
                (QuestionInstrument(p["instrument"]), p["pair_index"]) for p in live
            }

            existing_result = await db.execute(
                select(QuestionPair).where(QuestionPair.locale == locale)
            )
            existing_by_key = {
                (p.instrument, p.pair_index): p for p in existing_result.scalars().all()
            }

            for data in live:
                instrument = QuestionInstrument(data["instrument"])
                age_tier = AgeGroup(data["age_tier"])
                question_a_id = order_to_id[data["question_a_order"]]
                question_b_id = order_to_id[data["question_b_order"]]
                frame = _text(data["frame"], locale)
                option_a_text = _text(data.get("option_a_text"), locale)
                option_b_text = _text(data.get("option_b_text"), locale)
                option_a_icon = data.get("option_a_icon")
                option_b_icon = data.get("option_b_icon")

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
                    if sync_fields(existing, {
                        "frame": frame,
                        "option_a_text": option_a_text,
                        "option_b_text": option_b_text,
                        "option_a_icon": option_a_icon,
                        "option_b_icon": option_b_icon,
                    }):
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
                    frame=frame,
                    option_a_text=option_a_text,
                    option_b_text=option_b_text,
                    option_a_icon=option_a_icon,
                    option_b_icon=option_b_icon,
                    locale=locale,
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
        print(f"Bank: {len(PAIRS)} logical pairs x locales {PAIR_LOCALES}")


if __name__ == "__main__":
    asyncio.run(main())
