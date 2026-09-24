import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import pick_locale
from app.models.question import Question, QuestionInstrument
from app.schemas.question import QuestionResponse
def _bigfive_scale(question: Question) -> bool:
    return question.instrument == QuestionInstrument.big_five


def to_response_schema(
    question: Question, order: int | None = None, locale: str | None = None
) -> QuestionResponse:

    return QuestionResponse(
        id=question.id,
        instrument=question.instrument,
        riasec_type=question.riasec_type,
        bigfive_domain=question.bigfive_domain,
        text=pick_locale(question.text, locale),
        order=order if order is not None else question.order,
        bigfive_scale=_bigfive_scale(question),
    )


# Backwards-compatible alias — the validity-interleave splicing (PRO-298)
# below always calls with an explicit renumbered `order`.
_to_response = to_response_schema


async def get_all_questions(
    db: AsyncSession,
    *,
    assessment_id: uuid.UUID | None = None,
    locale: str | None = None,
) -> list[QuestionResponse]:
    """The Likert battery for one assessment."""
    result = await db.execute(select(Question).order_by(Question.order))
    questions = list(result.scalars().all())

    return [to_response_schema(q, i + 1, locale) for i, q in enumerate(questions)]
