import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import AgeGroup
from app.models.question import Question, QuestionInstrument
from app.schemas.question import QuestionResponse
from app.services.age_tiers import visible_tiers
from app.services.validity_battery import interleave_validity

# What `instrument='validity'` items are disguised as on the wire (PRO-298):
# they are now spliced into the RIASEC block (see get_all_questions), so they
# are wire-tagged `riasec` to match their neighbours' `instrument` field. The
# stored row keeps `instrument='validity'`; only this outbound DTO lies.
_VALIDITY_WIRE_INSTRUMENT = QuestionInstrument.riasec


def _bigfive_scale(question: Question) -> bool:
    """MC-SDS / infrequency items are worded as agree/disagree statements
    ("Я всегда…", "Я никогда…"), not RIASEC's "Мне нравится…" liking
    statements, so they must keep rendering on Big Five's "Точно…Неточно"
    scale even though they now sit inside the RIASEC block on the wire."""
    if question.instrument == QuestionInstrument.validity:
        return True
    return question.instrument == QuestionInstrument.big_five


def _to_response(question: Question, order: int) -> QuestionResponse:
    if question.instrument == QuestionInstrument.validity:
        return QuestionResponse(
            id=question.id,
            instrument=_VALIDITY_WIRE_INSTRUMENT,
            riasec_type=None,
            bigfive_domain=None,
            text=question.text,
            order=order,
            bigfive_scale=_bigfive_scale(question),
        )
    return QuestionResponse(
        id=question.id,
        instrument=question.instrument,
        riasec_type=question.riasec_type,
        bigfive_domain=question.bigfive_domain,
        text=question.text,
        order=order,
        bigfive_scale=_bigfive_scale(question),
    )


async def get_all_questions(
    db: AsyncSession, age_group: AgeGroup, *, assessment_id: uuid.UUID
) -> list[QuestionResponse]:
    """The Likert battery for one assessment. Protocol-validity items
    (PRO-298) are mixed into the RIASEC block by a rule that is
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

    # Splice validity items into the contiguous RIASEC sub-run only, so each
    # one sits among RIASEC-instrument-tagged items and its wire `instrument`
    # matches its neighbours (it keeps Big Five's scale via `bigfive_scale`
    # regardless — see _bigfive_scale). `base` is already `order`-sorted, and
    # every bank lays its instrument down as one contiguous `order` block, so
    # the run is a simple slice.
    first = next(
        (i for i, q in enumerate(base) if q.instrument == QuestionInstrument.riasec),
        None,
    )
    if first is None:  # no RIASEC block (junior: riasec rows are excluded above)
        sequence = interleave_validity(base, validity, seed=assessment_id.int)
    else:
        last = max(
            i
            for i, q in enumerate(base)
            if q.instrument == QuestionInstrument.riasec
        )
        woven = interleave_validity(
            base[first : last + 1], validity, seed=assessment_id.int
        )
        sequence = base[:first] + woven + base[last + 1 :]

    return [_to_response(q, i + 1) for i, q in enumerate(sequence)]
