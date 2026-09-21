"""RIASEC scoring, meta-characteristics, and career matching — see riasec-methodology.md."""

import uuid
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import pick_locale
from app.models.direction import Direction
from app.models.profile import AgeGroup
from app.models.question import HollandType, Question, QuestionInstrument
from app.models.user_response import UserResponse
from app.services.age_tiers import visible_tiers
from app.services.riasec_content import type_activities
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
    Kept for the code-based fallback path (directions without `onet_vector`)
    and for unit coverage of the legacy Iachan-style weights."""
    position = direction_code.find(letter)
    return 3 - position if 0 <= position < 3 else 0


# Perfect alignment under positional 3/2/1 × 3/2/1 weights (PRO-385 fallback).
_CODE_MATCH_MAX = 14


def career_match_score(user_code: list[str], direction_code: str) -> int:
    """Legacy positional congruence (0..14). Used only when a direction has
    no O*NET 6-dim vector — see `direction_match_score`."""
    user_weights = [3, 2, 1]
    return sum(
        w * direction_letter_weight(letter, direction_code)
        for w, letter in zip(user_weights, user_code)
    )


def pearson_correlation(user: dict[str, float], profession: dict[str, float]) -> float:
    """Pearson r between two 6-dim RIASEC profiles (shape similarity, -1..+1).

    Absolute scale differences cancel out — only whether the two profiles
    rise and fall on the same letters matters. Zero-variance inputs (flat
    profile) return 0.0 rather than NaN."""
    xs = [float(user.get(t, 0.0)) for t in HOLLAND_ORDER]
    ys = [float(profession.get(t, 0.0)) for t in HOLLAND_ORDER]
    mean_x = sum(xs) / len(HOLLAND_ORDER)
    mean_y = sum(ys) / len(HOLLAND_ORDER)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = sum((x - mean_x) ** 2 for x in xs)
    den_y = sum((y - mean_y) ** 2 for y in ys)
    if den_x == 0.0 or den_y == 0.0:
        return 0.0
    return num / (den_x * den_y) ** 0.5


def _has_onet_vector(direction: Direction) -> bool:
    vector = direction.onet_vector
    return isinstance(vector, dict) and all(t in vector for t in HOLLAND_ORDER)


def direction_match_score(normalized: dict[str, float], direction: Direction) -> float:
    """Primary: Pearson r vs `onet_vector`. Fallback: legacy code score / 14.

    Fallback keeps the three catalog professions without a US SOC analogue
    (Военный / Дипломат / Госслужащий) rankable without inventing a vector.
    Dividing by `_CODE_MATCH_MAX` puts the legacy score on a 0..1 scale so it
    can sit in the same ordered list as Pearson r without dominating it."""
    if _has_onet_vector(direction):
        return round(pearson_correlation(normalized, direction.onet_vector), 4)  # type: ignore[arg-type]
    user_code = top_code(normalized)
    return round(career_match_score(user_code, direction.holland_code) / _CODE_MATCH_MAX, 4)


async def matched_careers(
    normalized: dict[str, float], db: AsyncSession, limit: int = 10
) -> list[tuple[Direction, float]]:
    """Rank directions by full-profile Pearson match (PRO-385).

    Takes the full 6-dim `normalized` profile — not a truncated top-3 code —
    so a 0.04pp swap between 2nd and 3rd letters can no longer flip the
    entire top-10. Names/descriptions are resolved by the caller via
    pick_locale."""
    directions = (await db.execute(select(Direction))).scalars().all()
    scored = [(d, direction_match_score(normalized, d)) for d in directions]
    # Tie-break on slug (ascending) so equal scores don't depend on DB row
    # order — same convention as top_code's HOLLAND_ORDER tie-break above.
    scored.sort(key=lambda pair: (-pair[1], pair[0].slug))
    return scored[:limit]


async def answer_evidence(
    assessment_id: uuid.UUID, db: AsyncSession, *, locale: str | None = None
) -> dict[str, dict]:
    """Per-type breakdown of the student's own RIASEC answers — what the
    interest_map level is actually made of (PRO-336).

    Returns {type: {"distribution": [n5, n4, n3, n2, n1], "liked": [...],
    "disliked": [...]}}. `liked` (answers >= 4) and `disliked` (<= 2) are
    statement texts, strongest answer first; ties prefer the later bank
    position, because each type's block lists abstract traits first and
    concrete activities after — activities read better as a quote.

    Not tier-filtered: only questions this assessment actually answered can
    appear, which is already the student's visible set. Empty dict for an
    assessment with no RIASEC answers (junior/MI)."""
    result = await db.execute(
        select(Question.riasec_type, Question.text, Question.order, UserResponse.answer_value)
        .join(UserResponse, UserResponse.question_id == Question.id)
        .where(
            UserResponse.assessment_id == assessment_id,
            Question.instrument == QuestionInstrument.riasec,
        )
    )
    evidence: dict[str, dict] = {}
    liked: dict[str, list[tuple[int, int, str]]] = {}
    disliked: dict[str, list[tuple[int, int, str]]] = {}
    for riasec_type, text, order, value in result.all():
        letter = riasec_type.value
        entry = evidence.setdefault(letter, {"distribution": [0, 0, 0, 0, 0]})
        if 1 <= value <= 5:
            entry["distribution"][5 - value] += 1
        statement_text = pick_locale(text, locale=locale) if isinstance(text, dict) else str(text)
        if value >= 4:
            liked.setdefault(letter, []).append((-value, -order, statement_text))
        elif value <= _AVERSION_MAX_VALUE:
            disliked.setdefault(letter, []).append((value, -order, statement_text))
    for letter, entry in evidence.items():
        entry["liked"] = [t for *_, t in sorted(liked.get(letter, []))]
        entry["disliked"] = [t for *_, t in sorted(disliked.get(letter, []))]
    return evidence


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
        reinforce.extend(type_activities().get(letter, [])[:2])

    compensate: list[str] = []
    for letter in weaknesses:
        if _aversion_ratio(letter, aversion_counts, counts) >= _AVERSION_DISQUALIFY_RATIO:
            continue
        compensate = type_activities().get(letter, [])[:2]
        break

    return {"reinforce": reinforce, "compensate": compensate}
