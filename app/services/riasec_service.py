"""RIASEC scoring, meta-characteristics, and career matching — see riasec-methodology.md."""

import uuid
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.direction import Direction
from app.models.profile import AgeGroup
from app.models.question import HollandType, Question, QuestionInstrument
from app.models.user_response import UserResponse
from app.services.age_tiers import visible_tiers
from app.services.riasec_content import TYPE_ACTIVITIES
from app.services.scoring_levels import LEVEL_HIGH_MIN, LEVEL_LOW_MAX, LEVEL_MEDIUM_MIN

HOLLAND_ORDER: list[str] = ["R", "I", "A", "S", "E", "C"]

# Answers at or below this value count as an explicit negative ("aversion").
_AVERSION_MAX_VALUE = 2

# Share of a type's answers that must be explicit negatives before that type
# is excluded from `strengths` even if it scores high (methodology §5.3: a
# strength must be a "устойчивый, непротиворечивый интерес").
_AVERSION_DISQUALIFY_RATIO = 0.3


async def question_counts(db: AsyncSession, age_group: AgeGroup) -> dict[str, int]:
    """Questions per type, scoped to what this age branch was actually shown
    — computed live, never hardcoded (bank/age tiering can change size)."""
    result = await db.execute(
        select(Question.riasec_type, func.count(Question.id))
        .where(
            Question.instrument == QuestionInstrument.riasec,
            Question.age_tier.in_(visible_tiers(age_group)),
        )
        .group_by(Question.riasec_type)
    )
    counts = {t.value: c for t, c in result.all()}
    return {t: counts.get(t, 0) for t in HOLLAND_ORDER}


async def raw_scores(assessment_id: uuid.UUID, db: AsyncSession, age_group: AgeGroup) -> dict[str, int]:
    result = await db.execute(
        select(Question.riasec_type, func.sum(UserResponse.answer_value))
        .join(UserResponse, UserResponse.question_id == Question.id)
        .where(
            UserResponse.assessment_id == assessment_id,
            Question.instrument == QuestionInstrument.riasec,
            Question.age_tier.in_(visible_tiers(age_group)),
        )
        .group_by(Question.riasec_type)
    )
    sums = {t.value: int(s) for t, s in result.all()}
    return {t: sums.get(t, 0) for t in HOLLAND_ORDER}


async def aversion(assessment_id: uuid.UUID, db: AsyncSession, age_group: AgeGroup) -> dict[str, int]:
    """Count of explicit-negative (<=2) answers per type."""
    result = await db.execute(
        select(Question.riasec_type, func.count(UserResponse.id))
        .join(UserResponse, UserResponse.question_id == Question.id)
        .where(
            UserResponse.assessment_id == assessment_id,
            UserResponse.answer_value <= _AVERSION_MAX_VALUE,
            Question.instrument == QuestionInstrument.riasec,
            Question.age_tier.in_(visible_tiers(age_group)),
        )
        .group_by(Question.riasec_type)
    )
    counts = {t.value: c for t, c in result.all()}
    return {t: counts.get(t, 0) for t in HOLLAND_ORDER}


def normalize(raw: dict[str, int], counts: dict[str, int]) -> dict[str, float]:
    """% of the MAXIMUM POSSIBLE score for that type (count * 5) — not self-relative.

    This differs deliberately from the old engine's normalize_scores(), which scaled
    against the student's own top category (always 100%). Here 100% means "answered
    the maximum on every question of this type" — a student may never hit it."""
    return {
        t: round(raw.get(t, 0) / (counts[t] * 5) * 100, 1) if counts.get(t) else 0.0
        for t in HOLLAND_ORDER
    }


def differentiation(normalized: dict[str, float]) -> float:
    values = normalized.values()
    return round(max(values) - min(values), 1) if values else 0.0


def _hexagon_distance(a: str, b: str) -> int:
    i, j = HOLLAND_ORDER.index(a), HOLLAND_ORDER.index(b)
    diff = abs(i - j)
    return min(diff, len(HOLLAND_ORDER) - diff)


def consistency(top2: list[str]) -> Literal["high", "medium", "low"]:
    if len(top2) < 2:
        return "high"
    distance = _hexagon_distance(top2[0], top2[1])
    if distance <= 1:
        return "high"
    if distance == 2:
        return "medium"
    return "low"


def top_code(normalized: dict[str, float], limit: int = 3) -> list[str]:
    # Tie-break: fixed HOLLAND_ORDER position, so equal percentages are still
    # resolved deterministically (methodology §3, step 4).
    ranked = sorted(HOLLAND_ORDER, key=lambda t: (-normalized.get(t, 0.0), HOLLAND_ORDER.index(t)))
    return ranked[:limit]


def direction_letter_weight(letter: str, direction_code: str) -> int:
    """3 if `letter` is direction_code's primary (first) letter, 2 if
    secondary, 1 if tertiary, 0 if absent — positional, not just membership.
    Holland's own congruence theory (Iachan-style indices) treats matching
    a direction's PRIMARY letter as worth more than matching its third —
    plain `letter in direction_code` collapsed that distinction, which is
    also why every anagram of the same 3 letters (CSE/ESC/SEC/...) used to
    score identically (found live: report_v2_assembler.py's
    _matched_strengths_for produced byte-identical `why` text across
    unrelated careers sharing a letter set)."""
    position = direction_code.find(letter)
    return 3 - position if 0 <= position < 3 else 0


def career_match_score(user_code: list[str], direction_code: str) -> int:
    user_weights = [3, 2, 1]
    return sum(
        w * direction_letter_weight(letter, direction_code)
        for w, letter in zip(user_weights, user_code)
    )


async def matched_careers(
    user_code: list[str], db: AsyncSession, limit: int = 10
) -> list[tuple[Direction, int]]:
    result = await db.execute(select(Direction))
    directions = list(result.scalars().all())
    scored = [(d, career_match_score(user_code, d.holland_code)) for d in directions]
    # Tie-break on slug (ascending) so equal scores don't depend on DB row
    # order — same convention as top_code's HOLLAND_ORDER tie-break above.
    scored.sort(key=lambda pair: (-pair[1], pair[0].slug))
    # Used to drop every direction but one for an exact-duplicate
    # holland_code here (found live: 3 of 5 careers shown to a student all
    # had holland_code=="CSE", reading as the app repeating itself) — but
    # that also permanently hid every OTHER direction sharing that code from
    # EVERY student, no matter how well any of them actually fit, which
    # stopped scaling once the catalog grew past ~120 directions (more
    # entries than there are distinct 3-distinct-letter codes, so exact
    # collisions become unavoidable). The repetition problem this was
    # guarding against is now handled correctly downstream instead —
    # report_v2_assembler.py's build_riasec_careers gives any career sharing
    # already-shown matched evidence its own distinguishing clause (that
    # career's own skills_needed[0]) rather than repeating the sentence — so
    # nothing needs to be hidden here to avoid reading as copy-pasted.
    return scored[:limit]


def _aversion_ratio(letter: str, aversion_counts: dict[str, int], counts: dict[str, int]) -> float:
    total = counts.get(letter, 0)
    return (aversion_counts.get(letter, 0) / total) if total else 0.0


def strengths_weaknesses(
    normalized: dict[str, float],
    aversion_counts: dict[str, int],
    counts: dict[str, int],
    limit: int = 3,
) -> tuple[list[str], list[str]]:
    """Build up to `limit` strengths in three tiers of decreasing confidence,
    so the "Сильные стороны" section stays populated for an ordinary profile
    without ever promoting a genuinely weak type:

    1. Types that clear LEVEL_HIGH_MIN (the same bar interest_map uses for
       "high") AND aren't explicitly disliked (aversion) — the real signal.
    2. Still short of `limit`? Any remaining type >= LEVEL_MEDIUM_MIN, by
       rank, aversion ignored (career matching / top_code ignores it too).
       A mid-band score is softer evidence but it's still the student's own
       relative high, and 50-70 is interest_map's neutral "medium" band —
       so citing it here doesn't contradict that section the way a
       floor-level type would.
    3. Never a type below LEVEL_MEDIUM_MIN. Found live: a profile of
       I=100/A=100/R=C=E=S=20 had R (tied with two "weaknesses") padded into
       `strengths` by the old blind top-3 and then cited as matched evidence
       in 7 of 10 careers — that's the case this floor prevents. So a
       profile with fewer than `limit` types at >= LEVEL_MEDIUM_MIN still
       returns fewer than `limit` (even zero — the flat profile is surfaced
       elsewhere via differentiation/is_flat_profile).

    Weaknesses get the mirror-image bar (<= LEVEL_LOW_MAX) — a mid-pack
    score isn't a confirmed weakness either."""
    ranked = sorted(HOLLAND_ORDER, key=lambda t: (-normalized.get(t, 0.0), HOLLAND_ORDER.index(t)))

    strengths = [
        t for t in ranked
        if normalized.get(t, 0.0) >= LEVEL_HIGH_MIN
        and _aversion_ratio(t, aversion_counts, counts) < _AVERSION_DISQUALIFY_RATIO
    ][:limit]
    if len(strengths) < limit:
        for t in ranked:
            if len(strengths) >= limit:
                break
            if t not in strengths and normalized.get(t, 0.0) >= LEVEL_MEDIUM_MIN:
                strengths.append(t)

    weaknesses = [t for t in reversed(ranked) if normalized.get(t, 0.0) <= LEVEL_LOW_MAX][:limit]

    return strengths, weaknesses


def development_plan(
    code: list[str],
    weaknesses: list[str],
    aversion_counts: dict[str, int],
    counts: dict[str, int],
) -> dict[str, list[str]]:
    """Methodology §5.4: reinforce the top code, offer a compensating activity for
    the single weakest type — unless the student explicitly dislikes it (aversion)."""
    reinforce: list[str] = []
    for letter in code:
        reinforce.extend(TYPE_ACTIVITIES.get(letter, [])[:2])

    compensate: list[str] = []
    for letter in weaknesses:
        if _aversion_ratio(letter, aversion_counts, counts) >= _AVERSION_DISQUALIFY_RATIO:
            continue
        compensate = TYPE_ACTIVITIES.get(letter, [])[:2]
        break

    return {"reinforce": reinforce, "compensate": compensate}
