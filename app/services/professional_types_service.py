"""PRO-338 Ф1.2 — «Профессиональные типы» (ДДО) scoring: 1 point per А/Б
pick aggregated into 5 interest scales, the 5 raw abilities values kept
separate, and the hybrid-profile flag. See
Тикеты-новые-тесты/02-Фаза1-Лёгкие-тесты.md §1.А Ф1.2.

Scale->item mapping is resolved via `Question.order` against
professional_types_bank.py's own PAIRS/QUESTIONS data, not a DB column —
consistent with the Ф0.8/Ф1.1 "content+order only" decision: no scoring
metadata was ever written to the DB, so this is the one place that reads
the bank file directly instead of a model field (unlike riasec_type/
bigfive_domain, which get an actual column)."""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import pick_locale
from app.models.question import Question, QuestionInstrument
from app.models.user_response import UserResponse
from scripts.professional_types_bank import PAIRS, QUESTIONS

# Fixed order (Ч-П/Ч-Т/Ч-Ч/Ч-З/Ч-Х per the source spec) — used for the
# tie-break in hybrid_profile() and to guarantee every scale key is present
# in a returned dict even when it scored 0.
SCALE_ORDER: list[str] = ["practical", "technical", "social", "sign", "artistic"]

# question_pair_service._PICKED_VALUE — duplicated here (not imported) since
# that name is private to its own module; both mean the same "this option
# was the one picked" answer_value.
_PICKED_VALUE = 5

_INTEREST_ORDER_TO_SCALE: dict[int, str] = {
    option["order"]: option["scale"]
    for pair in PAIRS
    for option in (pair["option_a"], pair["option_b"])
}
_ABILITIES_ORDER_TO_SCALE: dict[int, str] = {q["order"]: q["scale"] for q in QUESTIONS}


async def interest_raw_scores(assessment_id: uuid.UUID, db: AsyncSession) -> dict[str, int] | None:
    """1 point per picked option, summed into its scale. `None` when the
    student hasn't answered any of the 20 pairs yet (never taken this test,
    e.g. junior/middle, or a senior assessment still in progress) — not a
    zero-filled dict, which would misreport "took the test, scored nothing
    everywhere" as if it were real data."""
    result = await db.execute(
        select(Question.order)
        .join(UserResponse, UserResponse.question_id == Question.id)
        .where(
            Question.instrument == QuestionInstrument.professional_types,
            UserResponse.assessment_id == assessment_id,
            UserResponse.answer_value == _PICKED_VALUE,
        )
    )
    picked_orders = result.scalars().all()
    if not picked_orders:
        return None

    scores = dict.fromkeys(SCALE_ORDER, 0)
    for order in picked_orders:
        scores[_INTEREST_ORDER_TO_SCALE[order]] += 1
    return scores


async def abilities_raw_scores(assessment_id: uuid.UUID, db: AsyncSession) -> dict[str, int] | None:
    """The 5 raw 0-3 Likert values, one per scale — read verbatim from
    `UserResponse.answer_value` (professional_types_abilities' own scale is
    genuinely 0-3, not a shifted 1-5 — see app/schemas/response.py).
    `None` when none of the 5 have been answered yet, same reasoning as
    interest_raw_scores(). Never merged with interest scores — the Radar
    Chart (Ф1.3) draws them as two separate overlaid polygons."""
    result = await db.execute(
        select(Question.order, UserResponse.answer_value)
        .join(UserResponse, UserResponse.question_id == Question.id)
        .where(
            Question.instrument == QuestionInstrument.professional_types_abilities,
            UserResponse.assessment_id == assessment_id,
        )
    )
    rows = result.all()
    if not rows:
        return None
    return {_ABILITIES_ORDER_TO_SCALE[order]: value for order, value in rows}


async def interest_evidence(assessment_id: uuid.UUID, db: AsyncSession) -> dict[str, dict] | None:
    """Per-scale breakdown of the student's own 20 А/Б picks — for each
    scale, how many times it appeared across the 20 pairs and how many of
    those appearances it was actually picked, plus the literal option text
    per appearance (question_pair_service writes picked=5/other=1 for BOTH
    options of an answered pair, so every appearance — picked or not — has
    its own `UserResponse` row here). `None` when none of the 20 pairs have
    been answered yet."""
    result = await db.execute(
        select(Question.order, Question.text, UserResponse.answer_value)
        .join(UserResponse, UserResponse.question_id == Question.id)
        .where(
            Question.instrument == QuestionInstrument.professional_types,
            UserResponse.assessment_id == assessment_id,
        )
        .order_by(Question.order)
    )
    rows = result.all()
    if not rows:
        return None

    evidence: dict[str, dict] = {scale: {"picked": 0, "total": 0, "items": []} for scale in SCALE_ORDER}
    for order, text, value in rows:
        scale = _INTEREST_ORDER_TO_SCALE[order]
        picked = value == _PICKED_VALUE
        entry = evidence[scale]
        entry["total"] += 1
        if picked:
            entry["picked"] += 1
        entry["items"].append({
            "text": pick_locale(text) if isinstance(text, dict) else str(text),
            "picked": picked,
        })
    return evidence


async def abilities_evidence(assessment_id: uuid.UUID, db: AsyncSession) -> dict[str, dict] | None:
    """The literal text + raw 0-3 value behind each of the 5 abilities
    scores — one item per scale, so there's no distribution to bucket,
    unlike every other evidence builder here. `None` when none of the 5
    have been answered yet."""
    result = await db.execute(
        select(Question.order, Question.text, UserResponse.answer_value)
        .join(UserResponse, UserResponse.question_id == Question.id)
        .where(
            Question.instrument == QuestionInstrument.professional_types_abilities,
            UserResponse.assessment_id == assessment_id,
        )
    )
    rows = result.all()
    if not rows:
        return None
    return {
        _ABILITIES_ORDER_TO_SCALE[order]: {
            "text": pick_locale(text) if isinstance(text, dict) else str(text),
            "value": value,
        }
        for order, text, value in rows
    }


def hybrid_profile(interest_scores: dict[str, int] | None) -> list[str] | None:
    """[scale_a, scale_b] when the top two interest scales are within 1
    point of each other (a near-tie for "leading" interest) — otherwise
    `None`. No pre-baked list of example professions: the source spec's
    "инженер-программист" for a technical+sign hybrid is illustrative only,
    the specialist reads the raw scores and decides themselves (Ф1.2 scope
    decision, matches the epic's "Own scales" policy).

    Ties within the top two are broken by SCALE_ORDER (Ч-П/Ч-Т/Ч-Ч/Ч-З/Ч-Х),
    same convention as riasec_service.top_code — deterministic, never
    dict-iteration-order-dependent."""
    if not interest_scores:
        return None
    ranked = sorted(
        interest_scores.items(),
        key=lambda item: (-item[1], SCALE_ORDER.index(item[0])),
    )
    top, second = ranked[0], ranked[1]
    if top[1] - second[1] <= 1:
        return [top[0], second[0]]
    return None
