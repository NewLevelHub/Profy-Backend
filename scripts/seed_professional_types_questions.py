"""
Seed script: populate «Профессиональные типы» (ДДО) content from
professional_types_bank.py — the 5-item `professional_types_abilities`
Likert block (QUESTIONS) AND the 20 forced-choice "интересы" pairs (PAIRS):
40 dedicated backing `questions` rows (instrument='professional_types') +
20 `question_pairs` rows. PRO-338 Ф1.1, pattern 1:1 with
seed_riasec_questions.py for the Likert half (originally the lie-scale seed,
removed in PRO-388) — self-contained, like every other single-instrument
bank (RIASEC/BigFive) that owns its own seed script end-to-end.

Run inside Docker, AFTER seed_bigfive_questions.py (shares the same `order`
numbering space, contiguous so the battery renders the
Likert half as one unbroken "Дополнительные тесты" sub-section, not
interleaved):
    docker-compose exec api python scripts/seed_professional_types_questions.py

Idempotent, self-healing: each of the 3 row groups (abilities questions,
pair-option questions, pairs) upserts by its own stable key and deletes any
DB row whose key is no longer in the bank — same pattern as every other
seed_*.py script.
"""
import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.question import Question, QuestionInstrument
from app.models.question_pair import QuestionPair
from app.services.admin_lock import has_overrides, sync_fields
from scripts.professional_types_bank import PAIRS, QUESTIONS


async def _seed_abilities(db: AsyncSession) -> tuple[int, int, int, int]:
    live_orders = {q["order"] for q in QUESTIONS}

    existing_result = await db.execute(
        select(Question).where(Question.instrument == QuestionInstrument.professional_types_abilities)
    )
    existing_by_order = {q.order: q for q in existing_result.scalars().all()}

    inserted = updated = skipped = deleted = 0

    for data in QUESTIONS:
        # `Question.text` is `{locale: str}` JSONB (docs/i18n-contract.md §8)
        # — the bank already builds this dict itself (kk added PRO-338
        # Ф4.4, see professional_types_bank.py's own `_abilities_text`
        # helper), so this is passed straight through.
        text = data["text"]
        existing = existing_by_order.get(data["order"])

        if existing is not None:
            changed = sync_fields(existing, {"text": text})
            updated += 1 if changed else 0
            skipped += 0 if changed else 1
            continue

        db.add(Question(
            instrument=QuestionInstrument.professional_types_abilities,
            text=text, order=data["order"],
        ))
        inserted += 1

    for order, question in existing_by_order.items():
        if order not in live_orders and not has_overrides(question):
            await db.delete(question)
            deleted += 1

    return inserted, updated, skipped, deleted


async def _seed_pair_options(db: AsyncSession) -> tuple[dict[int, uuid.UUID], tuple[int, int, int, int]]:
    """Seeds the 40 dedicated backing Question rows (one per pair option),
    instrument='professional_types'. Returns an order->id map for
    `_seed_pairs` to resolve `question_a_id`/`question_b_id` from."""
    options = [
        option
        for pair in PAIRS
        for option in (pair["option_a"], pair["option_b"])
    ]
    live_orders = {o["order"] for o in options}

    existing_result = await db.execute(
        select(Question).where(Question.instrument == QuestionInstrument.professional_types)
    )
    existing_by_order = {q.order: q for q in existing_result.scalars().all()}

    inserted = updated = skipped = deleted = 0

    for data in options:
        # `Question.text` is `{locale: str}` JSONB (docs/i18n-contract.md §8)
        # — the bank already builds this dict itself (kk added PRO-338
        # Ф4.4, see professional_types_bank.py's own `_KK_PAIR_TEXT`
        # fold-in), so this is passed straight through.
        text = data["text"]
        existing = existing_by_order.get(data["order"])

        if existing is not None:
            changed = sync_fields(existing, {"text": text})
            updated += 1 if changed else 0
            skipped += 0 if changed else 1
            continue

        question = Question(
            instrument=QuestionInstrument.professional_types,
            text=text, order=data["order"],
        )
        db.add(question)
        existing_by_order[data["order"]] = question
        inserted += 1

    for order, question in list(existing_by_order.items()):
        if order not in live_orders and not has_overrides(question):
            await db.delete(question)
            del existing_by_order[order]
            deleted += 1

    await db.flush()
    order_to_id = {order: q.id for order, q in existing_by_order.items()}
    return order_to_id, (inserted, updated, skipped, deleted)


async def _seed_pairs(db: AsyncSession, order_to_id: dict[int, uuid.UUID]) -> tuple[int, int, int, int]:
    live_indices = {p["pair_index"] for p in PAIRS}

    existing_result = await db.execute(
        select(QuestionPair).where(QuestionPair.instrument == QuestionInstrument.professional_types)
    )
    existing_by_index = {p.pair_index: p for p in existing_result.scalars().all()}

    inserted = updated = skipped = deleted = 0

    for data in PAIRS:
        question_a_id = order_to_id[data["option_a"]["order"]]
        question_b_id = order_to_id[data["option_b"]["order"]]
        existing = existing_by_index.get(data["pair_index"])

        if existing is not None:
            changed = sync_fields(existing, {
                "question_a_id": question_a_id,
                "question_b_id": question_b_id,
            })
            updated += 1 if changed else 0
            skipped += 0 if changed else 1
            continue

        db.add(QuestionPair(
            instrument=QuestionInstrument.professional_types,
            pair_index=data["pair_index"],
            question_a_id=question_a_id,
            question_b_id=question_b_id,
        ))
        inserted += 1

    for index, pair in existing_by_index.items():
        if index not in live_indices and not has_overrides(pair):
            await db.delete(pair)
            deleted += 1

    return inserted, updated, skipped, deleted


async def main() -> None:
    async with async_session() as db:
        ability_counts = await _seed_abilities(db)
        order_to_id, option_counts = await _seed_pair_options(db)
        pair_counts = await _seed_pairs(db, order_to_id)

        await db.commit()

        for label, (inserted, updated, skipped, deleted) in (
            ("professional_types_abilities questions", ability_counts),
            ("professional_types pair-option questions", option_counts),
            ("professional_types pairs", pair_counts),
        ):
            print(
                f"{label} — inserted: {inserted}, updated: {updated}, "
                f"skipped (unchanged): {skipped}, orphans deleted: {deleted}"
            )
        print(
            f"Total: {len(QUESTIONS)} abilities items, {len(PAIRS)} pairs "
            f"({len(PAIRS) * 2} pair-option questions)"
        )


if __name__ == "__main__":
    asyncio.run(main())
