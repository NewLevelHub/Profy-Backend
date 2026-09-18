"""PRO-338 Ф1.5/Ф1.6 — Eysenck EPI «Темперамент»: 1 point per key match on
each of the 3 scales (Экстраверсия-интроверсия/Нейротизм/Шкала лжи), band
labels from `app.config.eysenck_thresholds`, the lie-scale traffic-light
flag, and the quadrant (temperament) classification. See
Тикеты-новые-тесты/02-Фаза1-Лёгкие-тесты.md §1.Б Ф1.5/Ф1.6.

Scale/keyed-direction is resolved via `Question.order` against
eysenck_bank.py's own QUESTIONS data (no DB column) — same approach as
app/services/professional_types_service.py, consistent with the Ф0.8
"content+order only" decision (no scoring metadata was ever written to the
DB for this epic's new instruments)."""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import EysenckThresholds, eysenck_thresholds
from app.i18n import pick_locale
from app.models.question import Question, QuestionInstrument
from app.models.user_response import UserResponse
from scripts.eysenck_bank import QUESTIONS

# YES_NO_SCALE frontend convention (app/schemas/response.py, Ф0.5): 1=Нет, 2=Да.
_YES_VALUE = 2
_NO_VALUE = 1

_ORDER_TO_KEY: dict[int, tuple[str, str]] = {
    q["order"]: (q["scale"], q["keyed"]) for q in QUESTIONS
}

# Both scales' raw range is 0-24 (24 keyed items each — see eysenck_bank.py's
# per-scale item counts) — the midpoint is the quadrant split for both axes,
# independent from extraversion_level/neuroticism_level's own (finer-grained,
# 5- and 4-band) thresholds above. Classic Eysenck personality-circle
# mapping (Тикеты-новые-тесты/02-Фаза1-Лёгкие-тесты.md §1.Б Ф1.6's "сильный/
# слабый х уравновешенный/неуравновешенный х подвижный/инертный" formula):
# extraversion >= midpoint = "подвижный" (mobile) side, neuroticism >=
# midpoint = "неуравновешенный" (unbalanced) side.
_QUADRANT_MIDPOINT = 12


async def raw_scores(assessment_id: uuid.UUID, db: AsyncSession) -> dict[str, int] | None:
    """1 point per item whose answer matches its own keyed direction
    (extraversion/neuroticism items keyed "yes" score on Да=2, items keyed
    "no" score on Нет=1 — see eysenck_bank.py's per-item `keyed` field).
    `None` when nothing has been answered yet (junior/middle never see this
    senior-only content, or a senior assessment still in progress) — not a
    zero-filled dict, which would misreport "took it, scored nothing
    everywhere" as if it were real data."""
    result = await db.execute(
        select(Question.order, UserResponse.answer_value)
        .join(UserResponse, UserResponse.question_id == Question.id)
        .where(
            Question.instrument == QuestionInstrument.eysenck,
            UserResponse.assessment_id == assessment_id,
        )
    )
    rows = result.all()
    if not rows:
        return None

    scores = {"extraversion": 0, "neuroticism": 0, "lie": 0}
    for order, answer_value in rows:
        scale, keyed = _ORDER_TO_KEY[order]
        keyed_value = _YES_VALUE if keyed == "yes" else _NO_VALUE
        if answer_value == keyed_value:
            scores[scale] += 1
    return scores


async def answer_evidence(assessment_id: uuid.UUID, db: AsyncSession) -> dict[str, dict] | None:
    """Per-scale breakdown of the student's own Eysenck answers — the same
    "what is this raw score actually made of" evidence
    riasec_service.answer_evidence provides for RIASEC, mirrored here for
    the psychologist report's "Почему такой результат" card (parity request:
    the specialist screen should show real answers, not just a restated
    score).

    Returns {scale: {"answered", "yes", "no", "items": [{"text","answer"}]}}
    for each of extraversion/neuroticism/lie — `answer` is the student's
    literal Да/Нет, not whether it matched the keyed direction. `None` when
    nothing has been answered yet, same convention as `raw_scores()`."""
    result = await db.execute(
        select(Question.order, Question.text, UserResponse.answer_value)
        .join(UserResponse, UserResponse.question_id == Question.id)
        .where(
            Question.instrument == QuestionInstrument.eysenck,
            UserResponse.assessment_id == assessment_id,
        )
        .order_by(Question.order)
    )
    rows = result.all()
    if not rows:
        return None

    evidence: dict[str, dict] = {}
    for order, text, value in rows:
        scale, _keyed = _ORDER_TO_KEY[order]
        answer = "yes" if value == _YES_VALUE else "no"
        entry = evidence.setdefault(scale, {"answered": 0, "yes": 0, "no": 0, "items": []})
        entry["answered"] += 1
        entry[answer] += 1
        entry["items"].append({
            "text": pick_locale(text) if isinstance(text, dict) else str(text),
            "answer": answer,
        })
    return evidence


def quadrant(extraversion_raw: int, neuroticism_raw: int) -> str:
    """One of the 4 classic Eysenck temperaments, from which side of the
    (12, 12) midpoint each raw score falls on:
      extravert + unstable -> choleric
      extravert + stable   -> sanguine
      introvert + stable   -> phlegmatic
      introvert + unstable -> melancholic
    Ties at exactly 12 fall on the "extravert"/"unstable" side (`>=`), same
    convention on both axes — an arbitrary but consistent choice, no source
    guidance for the exact boundary point."""
    extravert = extraversion_raw >= _QUADRANT_MIDPOINT
    unstable = neuroticism_raw >= _QUADRANT_MIDPOINT
    if extravert:
        return "choleric" if unstable else "sanguine"
    return "melancholic" if unstable else "phlegmatic"


def build_section_data(
    scores: dict[str, int] | None,
    *,
    thresholds: EysenckThresholds = eysenck_thresholds,
) -> dict | None:
    """Shapes `raw_scores()`'s output into the dict stored on
    `AnalysisResult.eysenck` / read back into `TemperamentSection`. `None`
    when `scores` is `None` (nothing answered) — same "as if the test
    doesn't exist" convention as professional_types_service."""
    if scores is None:
        return None
    return {
        "extraversion_raw": scores["extraversion"],
        "neuroticism_raw": scores["neuroticism"],
        "lie_scale_raw": scores["lie"],
        "extraversion_level": thresholds.extraversion_level(scores["extraversion"]),
        "neuroticism_level": thresholds.neuroticism_level(scores["neuroticism"]),
        "protocol_flagged": thresholds.lie_scale_flagged(scores["lie"]),
        "quadrant": quadrant(scores["extraversion"], scores["neuroticism"]),
    }
