"""Protocol-validity scoring (epic PRO-282, phase 1; PRO-299).

Computes every metric of the "шкала лжи" spec
(`docs/psych/psych-block-spec.md` §A) from one completed assessment and
persists the verdict:

  - MC-SDS raw score (`sd_raw`, 0–20) — 20 Likert answers folded to binary by
    the PRO-294 extreme-scoring rule and matched against the key;
  - `sd_level` — `sd_raw` bucketed against the versioned `sd_bounds` config;
  - LongString — longest run of identical raw answers across the whole Likert
    battery, in presentation order;
  - IRV — inter-item SD of the raw answers within the protocol;
  - `infrequency_failed` — attention-check traps whose folded answer differs
    from the only plausible one;
  - `careless_flag` — LongString ≥ / IRV ≤ / infrequency ≥ their configured
    flags, combined conservatively (any one trips it);
  - `traffic_light` — `red` on carelessness, else `yellow` when `sd_level` is
    `high` (sd_raw ≥ 16 — direct self-report compromised); `9–15`
    (`social_desirability`) is normative adolescent conformity and stays
    `green`, visible only in the breakdown (psych-block-spec.md §A5). A
    randomly-filled protocol makes the SD score uninformative anyway, so
    carelessness outranks it.

Mahalanobis D² is NOT in v1 (needs a normative covariance matrix from a
real sample) — `_d2_mahalanobis` is an explicit stub.

The verdict lands in `assessment_validity` (upserted — a retake overwrites),
a compact copy goes on `AnalysisResult.validity`, and one append-only row
goes to `validity_calibration_log` for every completed run. Triggered from
`report_service` right after the main report row is committed; a failure
here is logged and swallowed — the RIASEC/BigFive/MI report is returned no
matter what (эпик §4).
"""
import logging
import statistics
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import validity_thresholds
from app.models.analysis_result import AnalysisResult
from app.models.assessment_validity import AssessmentValidity, SdLevel, TrafficLight
from app.models.profile import AgeGroup
from app.models.question import Question, QuestionInstrument, ValidityRole
from app.models.user_response import UserResponse
from app.models.validity_calibration_log import ValidityCalibrationLog
from app.services import assessment_shared, question_service

logger = logging.getLogger(__name__)

# PRO-294 extreme-scoring fold of a 1–5 Likert answer. The midpoint "3" is
# neither pole (scores nothing) — doubt/moderation contradicts the "я
# всегда…/я никогда…" construct.
_AGREE_LIKERT = frozenset({4, 5})
_DISAGREE_LIKERT = frozenset({1, 2})

# IRV is meaningless on a stub battery — only let the "IRV too low" rule fire
# once the protocol is realistically long.
_MIN_BATTERY_FOR_IRV = 20


def _fold(answer: int | None) -> str | None:
    if answer in _AGREE_LIKERT:
        return "agree"
    if answer in _DISAGREE_LIKERT:
        return "disagree"
    return None  # midpoint 3, or unanswered


def _longest_run(values: list[int]) -> int:
    best = run = 0
    prev: object = object()
    for value in values:
        run = run + 1 if value == prev else 1
        prev = value
        best = max(best, run)
    return best


def _d2_mahalanobis() -> None:
    """Multivariate-outlier index for chaotic profiles (Meade & Craig 2012).

    TODO(PRO-299 v2): implement once ≥300–500 completed protocols give a
    normative covariance matrix (psych-block-spec.md §A6). Until then
    `careless_flag` rests on LongString + IRV + infrequency only — this is a
    deliberate stub, not a partial implementation.
    """
    return None


@dataclass(frozen=True)
class ValidityResult:
    sd_raw: int
    sd_level: SdLevel
    longstring_max: int
    irv: float
    infrequency_failed: int
    careless_flag: bool
    traffic_light: TrafficLight
    details: dict
    thresholds_version: int

    def container(self) -> dict:
        """Compact copy for `AnalysisResult.validity` + the `/result` section
        (PRO-300 reads the display fields off this / `assessment_validity`)."""
        return {
            "traffic_light": self.traffic_light.value,
            "sd_raw": self.sd_raw,
            "sd_level": self.sd_level.value,
            "longstring_max": self.longstring_max,
            "irv": round(self.irv, 3),
            "infrequency_failed": self.infrequency_failed,
            "careless_flag": self.careless_flag,
            "thresholds_version": self.thresholds_version,
        }


async def compute(
    assessment_id: uuid.UUID, db: AsyncSession, *, age_group: AgeGroup
) -> ValidityResult:
    """Pure-ish read: score the assessment, return the verdict. No writes."""
    thresholds = validity_thresholds

    # Presentation order (PRO-298 interleave) — LongString is "across the
    # whole battery" in the order the student actually saw the items.
    ordered_ids = [
        q.id
        for q in await question_service.get_all_questions(
            db, age_group, assessment_id=assessment_id
        )
    ]
    rows = (
        await db.execute(
            select(UserResponse.question_id, UserResponse.answer_value).where(
                UserResponse.assessment_id == assessment_id
            )
        )
    ).all()
    answer_by_qid: dict[uuid.UUID, int] = {qid: value for qid, value in rows}

    ordered_answers = [answer_by_qid[qid] for qid in ordered_ids if qid in answer_by_qid]
    longstring_max = _longest_run(ordered_answers)
    irv = statistics.pstdev(ordered_answers) if len(ordered_answers) >= 2 else 0.0

    # --- MC-SDS + infrequency: key / expected answer live in validity_meta ---
    validity_questions = (
        await db.execute(
            select(Question).where(Question.instrument == QuestionInstrument.validity)
        )
    ).scalars().all()

    sd_raw = 0
    infrequency_failed = 0
    sd_items: list[dict] = []
    infrequency_items: list[dict] = []
    for question in validity_questions:
        meta = question.validity_meta or {}
        answer = answer_by_qid.get(question.id)
        folded = _fold(answer)

        if question.validity_role == ValidityRole.sd_key:
            keyed = meta.get("keyed")
            scored = 1 if folded is not None and folded == keyed else 0
            sd_raw += scored
            sd_items.append(
                {"key": meta.get("key"), "keyed": keyed, "answer": answer, "scored": scored}
            )
        elif question.validity_role == ValidityRole.infrequency:
            expected = meta.get("expected_answer")
            failed = folded != expected
            infrequency_failed += 1 if failed else 0
            infrequency_items.append(
                {
                    "key": meta.get("key"),
                    "expected": expected,
                    "answer": answer,
                    "folded": folded,
                    "failed": failed,
                }
            )

    sd_level = SdLevel(thresholds.sd_level(sd_raw))

    reason_longstring = longstring_max >= thresholds.longstring_max_flag
    reason_irv = (
        len(ordered_answers) >= _MIN_BATTERY_FOR_IRV and irv <= thresholds.irv_low_flag
    )
    reason_infrequency = infrequency_failed >= thresholds.infrequency_fail_flag
    careless_flag = reason_longstring or reason_irv or reason_infrequency

    if careless_flag:
        traffic_light = TrafficLight.red
    elif sd_level is SdLevel.high:  # sd_raw >= 16; 9–15 is normative → green
        traffic_light = TrafficLight.yellow
    else:
        traffic_light = TrafficLight.green

    details = {
        "sd_items": sd_items,
        "infrequency_items": infrequency_items,
        "longstring": {"max_run": longstring_max, "battery_len": len(ordered_answers)},
        "irv": round(irv, 4),
        "careless_reasons": {
            "longstring": reason_longstring,
            "irv_low": reason_irv,
            "infrequency": reason_infrequency,
        },
        "d2_mahalanobis": _d2_mahalanobis(),  # v1 stub — always None
        "thresholds_version": thresholds.version,
        "sd_bounds": list(thresholds.sd_bounds),
    }

    return ValidityResult(
        sd_raw=sd_raw,
        sd_level=sd_level,
        longstring_max=longstring_max,
        irv=irv,
        infrequency_failed=infrequency_failed,
        careless_flag=careless_flag,
        traffic_light=traffic_light,
        details=details,
        thresholds_version=thresholds.version,
    )


_UPSERT_COLUMNS = (
    "sd_raw",
    "sd_level",
    "longstring_max",
    "irv",
    "infrequency_failed",
    "careless_flag",
    "traffic_light",
    "details",
    "rt_ms",
    "thresholds_version",
)


async def score_and_store(
    assessment_id: uuid.UUID,
    db: AsyncSession,
    *,
    age_group: AgeGroup,
    analysis: AnalysisResult | None = None,
) -> ValidityResult:
    """Compute the verdict and persist it: upsert `assessment_validity`
    (a retake overwrites the row), copy the compact form onto
    `AnalysisResult.validity`, append one `validity_calibration_log` row.
    Commits its own transaction — the caller has already committed the main
    report, so this is isolated from it."""
    result = await compute(assessment_id, db, age_group=age_group)

    # rt_ms — passively collected, NOT scored (PRO-298). Stored as raw
    # calibration data alongside the verdict.
    deltas = await assessment_shared.response_time_deltas_ms(assessment_id, db)

    values = {
        "assessment_id": assessment_id,
        "sd_raw": result.sd_raw,
        "sd_level": result.sd_level,
        "longstring_max": result.longstring_max,
        "irv": result.irv,
        "infrequency_failed": result.infrequency_failed,
        "careless_flag": result.careless_flag,
        "traffic_light": result.traffic_light,
        "details": result.details,
        "rt_ms": {"deltas_ms": deltas},
        "thresholds_version": result.thresholds_version,
    }
    stmt = pg_insert(AssessmentValidity).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["assessment_id"],
        set_={c: getattr(stmt.excluded, c) for c in _UPSERT_COLUMNS}
        | {"computed_at": func.now()},
    )
    await db.execute(stmt)

    if analysis is None:
        analysis = (
            await db.execute(
                select(AnalysisResult).where(
                    AnalysisResult.assessment_id == assessment_id
                )
            )
        ).scalar_one_or_none()
    if analysis is not None:
        analysis.validity = result.container()

    db.add(
        ValidityCalibrationLog(
            assessment_id=assessment_id,
            sd_raw=result.sd_raw,
            sd_level=result.sd_level,
            longstring_max=result.longstring_max,
            irv=result.irv,
            infrequency_failed=result.infrequency_failed,
            careless_flag=result.careless_flag,
            traffic_light=result.traffic_light,
            age_group=age_group,
            thresholds_version=result.thresholds_version,
        )
    )

    await db.commit()
    return result
