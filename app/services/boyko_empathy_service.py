"""PRO-338 Ф1.11 — Boyko empathy «Эмпатия»: 1 point per key match on each of
the 6 channels + the overall total (max 36), band label from
`app.config.boyko_empathy_thresholds`. See
Тикеты-новые-тесты/02-Фаза1-Лёгкие-тесты.md §1.Г Ф1.11.

Channel/keyed-direction is resolved via `Question.order` against
boyko_empathy_bank.py's own QUESTIONS data (no DB column) — same approach as
eysenck_service.py/elers_service.py, consistent with the Ф0.8 "content+order
only" decision."""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import BoykoEmpathyThresholds, boyko_empathy_thresholds
from app.models.question import Question, QuestionInstrument
from app.models.user_response import UserResponse
from scripts.boyko_empathy_bank import QUESTIONS

# YES_NO_SCALE frontend convention (app/schemas/response.py, Ф0.5): 1=Нет, 2=Да.
_YES_VALUE = 2
_NO_VALUE = 1

_ORDER_TO_KEY: dict[int, tuple[str, str]] = {q["order"]: (q["channel"], q["keyed"]) for q in QUESTIONS}

CHANNELS: tuple[str, ...] = ("rational", "emotional", "intuitive", "attitudes", "penetration", "identification")


async def raw_scores(assessment_id: uuid.UUID, db: AsyncSession) -> dict[str, int] | None:
    """1 point per item whose answer matches its own keyed direction, summed
    per channel. `None` when nothing has been answered yet (junior/middle
    never see this senior-only content, or a senior assessment still in
    progress) — not a zero-filled dict, which would misreport "took it,
    scored nothing everywhere" as if it were real data."""
    result = await db.execute(
        select(Question.order, UserResponse.answer_value)
        .join(UserResponse, UserResponse.question_id == Question.id)
        .where(
            Question.instrument == QuestionInstrument.boyko_empathy,
            UserResponse.assessment_id == assessment_id,
        )
    )
    rows = result.all()
    if not rows:
        return None

    scores = dict.fromkeys(CHANNELS, 0)
    for order, answer_value in rows:
        channel, keyed = _ORDER_TO_KEY[order]
        keyed_value = _YES_VALUE if keyed == "yes" else _NO_VALUE
        if answer_value == keyed_value:
            scores[channel] += 1
    return scores


def build_section_data(
    scores: dict[str, int] | None,
    *,
    thresholds: BoykoEmpathyThresholds = boyko_empathy_thresholds,
) -> dict | None:
    """Shapes `raw_scores()`'s output into the empathy half of the dict
    stored on `AnalysisResult.empathy_confidence` — the confidence half
    (kondash_anxiety_service.build_confidence_data) is merged in by
    report_service, since both instruments share one report section.
    `None` when `scores` is `None` (nothing answered)."""
    if scores is None:
        return None
    total = sum(scores.values())
    return {
        "empathy_channels": scores,
        "empathy_total": total,
        "empathy_level": thresholds.level(total),
    }
