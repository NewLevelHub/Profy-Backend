"""PRO-338 Ф1.11 — Kondash/Prikhozhan anxiety, «Соц. уверенность» half of
the Эмпатия+Уверенность report section: raw sum of the межличностная
(interpersonal) subscale (10 items, 0-4 each, max 40) -> sten 1-10 via the
age-bracketed "sten 10" threshold + the documented working proportional
formula -> confidence band. See
Тикеты-новые-тесты/02-Фаза1-Лёгкие-тесты.md §1.Г Ф1.11 and
app/data/kondash_anxiety_thresholds.json for the age-bracket/inversion
decisions this implements.

Subscale is resolved via `Question.order` against kondash_anxiety_bank.py's
own QUESTIONS data (no DB column) — same approach as every other Ф1
instrument service."""
import math
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import KondashAnxietyThresholds, kondash_anxiety_thresholds
from app.models.question import Question, QuestionInstrument
from app.models.user_response import UserResponse
from scripts.kondash_anxiety_bank import QUESTIONS

_ORDER_TO_SUBSCALE: dict[int, str] = {q["order"]: q["subscale"] for q in QUESTIONS}

_INTERPERSONAL = "interpersonal"


async def interpersonal_raw_score(assessment_id: uuid.UUID, db: AsyncSession) -> int | None:
    """Sum of the 10 межличностная-subscale items' raw 0-4 answers.
    `None` when nothing in this subscale has been answered yet (junior/
    middle never see this senior-only content, or a senior assessment still
    in progress) — not 0, which would misreport "took it, scored nothing"
    as if it were a real result."""
    result = await db.execute(
        select(Question.order, UserResponse.answer_value)
        .join(UserResponse, UserResponse.question_id == Question.id)
        .where(
            Question.instrument == QuestionInstrument.kondash_anxiety,
            UserResponse.assessment_id == assessment_id,
        )
    )
    rows = result.all()
    interpersonal_rows = [value for order, value in rows if _ORDER_TO_SUBSCALE[order] == _INTERPERSONAL]
    if not interpersonal_rows:
        return None
    return sum(interpersonal_rows)


def sten_from_raw(raw: int, sten10: int) -> int:
    """Working proportional scale (documented in
    docs/psych/new-tests-content-sources.md "Пробел 3" and mirrored in
    kondash_anxiety_thresholds.json's comment): linear interpolation from 0
    to the age's "sten 10" threshold, capped at 10 — a stopgap for stens
    1-9 until the full original raw->sten table is restored."""
    if sten10 <= 0:
        return 10
    return min(10, math.ceil(raw * 10 / sten10))


def build_confidence_data(
    interpersonal_raw: int | None,
    *,
    age: int,
    thresholds: KondashAnxietyThresholds = kondash_anxiety_thresholds,
) -> dict | None:
    """Shapes the raw межличностная score into the confidence half of the
    dict stored on `AnalysisResult.empathy_confidence` — the empathy half
    (boyko_empathy_service.build_section_data) is merged in by
    report_service, since both instruments share one report section. `None`
    when `interpersonal_raw` is `None` (nothing answered).

    `confidence_stens` is the SAME sten number the anxiety computation
    produces — no arithmetic 11-x inversion. The ticket's "инверсия" is the
    interpretive relationship (low anxiety sten = high confidence), applied
    only at the label level via `confidence_level`; the ticket's own band
    numbers (1-3 "высокая уверенность", 4-6 normative) are stated directly
    against the raw sten, not a flipped one — see kondash_anxiety_thresholds
    .json's own comment for the full reasoning."""
    if interpersonal_raw is None:
        return None
    sten10 = thresholds.interpersonal_sten10(age)
    sten = sten_from_raw(interpersonal_raw, sten10)
    return {
        "confidence_stens": sten,
        "confidence_level": thresholds.confidence_level(sten),
    }
