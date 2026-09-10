import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import AgeGroup
from app.models.question import Question, QuestionInstrument
from app.schemas.question import QuestionResponse
from app.services.age_tiers import visible_tiers
from app.services.validity_battery import interleave_validity

# What `instrument='validity'` items are disguised as on the wire (PRO-298):
# the client must not be able to tell a protocol-validity item from a Big Five
# one, and it selects the Likert scale by `instrument` — `big_five` gets the
# "неточно…точно" scale, which is the right one for the MC-SDS statements.
# The stored row keeps `instrument='validity'`; only this outbound DTO lies.
_VALIDITY_WIRE_INSTRUMENT = QuestionInstrument.big_five


def _to_response(question: Question, order: int) -> QuestionResponse:
    if question.instrument == QuestionInstrument.validity:
        return QuestionResponse(
            id=question.id,
            instrument=_VALIDITY_WIRE_INSTRUMENT,
            riasec_type=None,
            bigfive_domain=None,
            text=question.text,
            order=order,
        )
    return QuestionResponse(
        id=question.id,
        instrument=question.instrument,
        riasec_type=question.riasec_type,
        bigfive_domain=question.bigfive_domain,
        text=question.text,
        order=order,
    )


async def get_all_questions(
    db: AsyncSession, age_group: AgeGroup, *, assessment_id: uuid.UUID
) -> list[QuestionResponse]:
    """The Likert battery for one assessment. Protocol-validity items
    (PRO-298) are mixed into the Big Five block by a rule that is
    deterministic on `assessment_id` (same student → same battery) but not a
    fixed "every Nth" pattern; the whole sequence is then renumbered densely
    so the client, which re-sorts by `order`, renders exactly this order."""
    query = (
        select(Question)
        .where(Question.age_tier.in_(visible_tiers(age_group)))
        .order_by(Question.order)
    )
    if age_group == AgeGroup.junior:
        # Junior's stale `riasec`-tagged rows (retired in favor of MI, see
        # question_pair_service.get_pairs) would otherwise leak into the
        # plain Likert flow now that junior answers MI here too.
        query = query.where(Question.instrument != QuestionInstrument.riasec)
    result = await db.execute(query)
    questions = list(result.scalars().all())

    validity = [q for q in questions if q.instrument == QuestionInstrument.validity]
    base = [q for q in questions if q.instrument != QuestionInstrument.validity]
    if not validity:
        return [_to_response(q, i + 1) for i, q in enumerate(base)]

    # Splice validity items into the contiguous Big Five sub-run only, so each
    # one sits among Big-Five-scaled items and reads identically. `base` is
    # already `order`-sorted, and every bank lays its instrument down as one
    # contiguous `order` block, so the run is a simple slice.
    first = next(
        (i for i, q in enumerate(base) if q.instrument == QuestionInstrument.big_five),
        None,
    )
    if first is None:  # no Big Five block (shouldn't happen for a real battery)
        sequence = interleave_validity(base, validity, seed=assessment_id.int)
    else:
        last = max(
            i
            for i, q in enumerate(base)
            if q.instrument == QuestionInstrument.big_five
        )
        woven = interleave_validity(
            base[first : last + 1], validity, seed=assessment_id.int
        )
        sequence = base[:first] + woven + base[last + 1 :]

    return [_to_response(q, i + 1) for i, q in enumerate(sequence)]
