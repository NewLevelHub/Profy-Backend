"""PRO-338 Ф1.8 — Elers «Уровень притязаний»: sum of key matches (buffer
items excluded from the count but shown to the respondent like any other
question — see elers_bank.py), band label from `app.config.elers_thresholds`.
See Тикеты-новые-тесты/02-Фаза1-Лёгкие-тесты.md §1.В Ф1.8.

Keyed direction is resolved via `Question.order` against elers_bank.py's own
QUESTIONS data (no DB column) — same approach as eysenck_service.py/
professional_types_service.py, consistent with the Ф0.8 "content+order only"
decision (no scoring metadata was ever written to the DB for this epic's new
instruments)."""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ElersThresholds, elers_thresholds
from app.i18n import pick_locale
from app.models.question import Question, QuestionInstrument
from app.models.user_response import UserResponse
from scripts.elers_bank import QUESTIONS

# YES_NO_SCALE frontend convention (app/schemas/response.py, Ф0.5): 1=Нет, 2=Да.
_YES_VALUE = 2
_NO_VALUE = 1

_ORDER_TO_KEYED: dict[int, str] = {q["order"]: q["keyed"] for q in QUESTIONS}


async def raw_score(assessment_id: uuid.UUID, db: AsyncSession) -> int | None:
    """1 point per non-buffer item whose answer matches its own keyed
    direction (`keyed="yes"` scores on Да=2, `keyed="no"` scores on Нет=1,
    `keyed="buffer"` never scores regardless of answer). `None` when nothing
    has been answered yet (an assessment still in progress) — not 0, which would misreport
    "took it, scored nothing" as if it were a real result."""
    result = await db.execute(
        select(Question.order, UserResponse.answer_value)
        .join(UserResponse, UserResponse.question_id == Question.id)
        .where(
            Question.instrument == QuestionInstrument.elers,
            UserResponse.assessment_id == assessment_id,
        )
    )
    rows = result.all()
    if not rows:
        return None

    score = 0
    for order, answer_value in rows:
        keyed = _ORDER_TO_KEYED[order]
        if keyed == "buffer":
            continue
        keyed_value = _YES_VALUE if keyed == "yes" else _NO_VALUE
        if answer_value == keyed_value:
            score += 1
    return score


async def answer_evidence(assessment_id: uuid.UUID, db: AsyncSession) -> dict | None:
    """Breakdown of the student's own Elers answers — buffer items excluded,
    same as `raw_score()` (they never score, so they'd be noise here too).
    Single scale (unlike Eysenck's 3), so this returns one flat
    `{"answered", "yes", "no", "items": [{"text","answer"}]}` dict rather
    than a per-scale mapping. `None` when nothing scoreable has been
    answered yet."""
    result = await db.execute(
        select(Question.order, Question.text, UserResponse.answer_value)
        .join(UserResponse, UserResponse.question_id == Question.id)
        .where(
            Question.instrument == QuestionInstrument.elers,
            UserResponse.assessment_id == assessment_id,
        )
        .order_by(Question.order)
    )
    rows = [(order, text, value) for order, text, value in result.all() if _ORDER_TO_KEYED[order] != "buffer"]
    if not rows:
        return None

    entry = {"answered": 0, "yes": 0, "no": 0, "items": []}
    for order, text, value in rows:
        answer = "yes" if value == _YES_VALUE else "no"
        entry["answered"] += 1
        entry[answer] += 1
        entry["items"].append({
            "text": pick_locale(text) if isinstance(text, dict) else str(text),
            "answer": answer,
        })
    return entry


def build_section_data(
    score: int | None,
    *,
    thresholds: ElersThresholds = elers_thresholds,
) -> dict | None:
    """Shapes `raw_score()`'s output into the dict stored on
    `AnalysisResult.elers` / read back into `AspirationLevelSection`. `None`
    when `score` is `None` (nothing answered) — same "as if the test doesn't
    exist" convention as professional_types_service/eysenck_service."""
    if score is None:
        return None
    return {
        "score": score,
        "level": thresholds.level(score),
    }
