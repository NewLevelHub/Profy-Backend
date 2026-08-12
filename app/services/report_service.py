import json
import logging
import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.analysis_result import AnalysisResult
from app.models.artifact import Artifact
from app.models.assessment import Assessment, AssessmentStatus
from app.models.direction import Direction
from app.models.profile import AgeGroup, Profile
from app.prompts import report_summary
from app.schemas.result import AnalysisResultResponse
from app.services import (
    assessment_shared,
    bigfive_content,
    bigfive_service,
    llm_client,
    mi_service,
    motivation_pair_service,
    motivation_service,
    riasec_service,
    thinking_style_service,
)
from app.services.bigfive_content import strength_phrases
from app.services.mi_content import MI_LABELS
from app.services.motivation_content import highlight_phrases as motivation_highlight_phrases
from app.services.riasec_content import RIASEC_LABELS

logger = logging.getLogger(__name__)

CACHE_TTL = 60 * 60 * 24  # 24 hours

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def _career_dict(direction: Direction, match_score: int) -> dict:
    return {
        "slug": direction.slug,
        "name": direction.name,
        "holland_code": direction.holland_code,
        "match_score": match_score,
        "description": direction.description or "",
        "professions": list(direction.professions or []),
        "skills_needed": list(direction.skills_needed or []),
        "subjects_to_develop": list(direction.subjects_to_develop or []),
        "first_steps": list(direction.first_steps or []),
    }


def _build_summary(code: list[str]) -> str:
    if not code:
        return "Твои результаты показывают широкий потенциал для развития."
    labels = [RIASEC_LABELS.get(letter, letter) for letter in code]
    code_str = "".join(code)
    if len(labels) == 1:
        cats_str = labels[0]
    else:
        cats_str = ", ".join(labels[:-1]) + " и " + labels[-1]
    return (
        f"Твой код RIASEC — {code_str}. Сильнее всего у тебя выражены типы: {cats_str}. "
        f"Это подсказывает, в какую сторону тебе интересно и комфортно развиваться."
    )


def _build_junior_summary(code: list[str]) -> str:
    if not code:
        return "Твои результаты показывают широкий потенциал для развития."
    labels = [MI_LABELS.get(category, category) for category in code]
    if len(labels) == 1:
        cats_str = labels[0]
    else:
        cats_str = ", ".join(labels[:-1]) + " и " + labels[-1]
    return (
        f"Тебе больше всего интересно вот это: {cats_str}. "
        f"Это подсказывает, какие занятия и кружки стоит попробовать."
    )


async def _generate_ai_summary(
    profile: Profile | None,
    goal: str,
    code: list[str],
    strengths: list[str],
    careers: list[dict],
    artifacts: list,
    personality_highlights: list[str],
    motivation_highlights: list[str],
) -> str | None:
    """AI-personalized result summary. Returns None (→ template) if disabled or fails."""
    if profile is None or not llm_client.is_enabled():
        return None
    try:
        messages = report_summary.build_messages(
            profile, goal, code, strengths, careers, artifacts,
            personality_highlights, motivation_highlights,
        )
        raw = await llm_client.complete_json(
            messages, report_summary.SUMMARY_SCHEMA, "report_summary"
        )
    except (llm_client.LLMError, TypeError):
        logger.warning("AI summary failed, using template summary")
        return None
    summary = raw.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    return None


async def _assert_assessment_complete(
    assessment_id: uuid.UUID, age_group: AgeGroup, db: AsyncSession
) -> None:
    """Server-side re-check, independent of whatever `completed` flag a
    client last saw from /assessment/answers or /assessment/motivation —
    each of those only ever confirms its own phase, not the whole test.
    Required counts are age-specific since the MI/Harter merge: junior's
    Likert total is MI + Big Five with the retired RIASEC rows excluded
    (assessment_shared.likert_total_questions already does this), middle
    and senior are RIASEC + Big Five (question pairs land in the same
    Question/UserResponse tables, so no separate count is needed for them).
    Motivation is Harter pairs for junior/middle, MOST/LEAST triplets for
    senior — different tables, so the right counter has to be picked here."""
    likert_answered = await assessment_shared.likert_answered_count(assessment_id, db)
    likert_total = await assessment_shared.likert_total_questions(db, age_group)
    likert_done = likert_total > 0 and likert_answered >= likert_total

    if age_group == AgeGroup.senior:
        mot_answered = await motivation_service.answered_count(assessment_id, db)
        mot_total = await motivation_service.total_triplets(db)
    else:
        mot_answered = await motivation_pair_service.answered_count(assessment_id, db)
        mot_total = await motivation_pair_service.total_pairs(db)
    mot_done = mot_total > 0 and mot_answered >= mot_total

    if not (likert_done and mot_done):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Тест ещё не завершён — сначала ответь на все обязательные вопросы",
        )


async def build_report(
    assessment_id: uuid.UUID, db: AsyncSession
) -> AnalysisResultResponse:
    cache_key = f"report:{assessment_id}"
    redis = _get_redis()

    cached = await redis.get(cache_key)
    if cached:
        return AnalysisResultResponse.model_validate(json.loads(cached))

    existing_result = await db.execute(
        select(AnalysisResult).where(AnalysisResult.assessment_id == assessment_id)
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        response = AnalysisResultResponse.model_validate(existing)
        await redis.setex(cache_key, CACHE_TTL, response.model_dump_json())
        return response

    assessment_result = await db.execute(
        select(Assessment).where(Assessment.id == assessment_id)
    )
    assessment = assessment_result.scalar_one_or_none()
    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found"
        )

    profile_result = await db.execute(
        select(Profile).where(Profile.id == assessment.profile_id)
    )
    profile = profile_result.scalar_one_or_none()
    age_group = profile.age_group if profile is not None else AgeGroup.senior

    # Gate before any write: an incomplete assessment must not flip to
    # `completed` and must not get a partial AnalysisResult.
    await _assert_assessment_complete(assessment_id, age_group, db)

    artifacts_result = await db.execute(
        select(Artifact).where(Artifact.profile_id == assessment.profile_id)
    )
    artifacts = list(artifacts_result.scalars().all())

    if age_group == AgeGroup.junior:
        # Junior (6-9) is not career-oriented (TZ_Profi.md §4.1) — RIASEC and
        # its career matching are replaced with an MI-style "what to try"
        # instrument. Big Five stays unchanged below for personality/thinking_style.
        raw = await mi_service.raw_scores(assessment_id, db, age_group)
        counts = await mi_service.question_counts(db, age_group)
        profile_scores = mi_service.normalize(raw, counts)
        aversion_counts = await mi_service.aversion(assessment_id, db, age_group)

        code = mi_service.top_code(profile_scores)
        meta = {
            "differentiation": mi_service.differentiation(profile_scores),
            "consistency": mi_service.consistency(profile_scores),
            "aversion": aversion_counts,
        }
        strengths, weaknesses = mi_service.strengths_weaknesses(profile_scores, aversion_counts, counts)
        plan = mi_service.development_plan(code, weaknesses, aversion_counts, counts)
        careers: list[dict] = []
    else:
        raw = await riasec_service.raw_scores(assessment_id, db, age_group)
        counts = await riasec_service.question_counts(db, age_group)
        profile_scores = riasec_service.normalize(raw, counts)
        aversion_counts = await riasec_service.aversion(assessment_id, db, age_group)

        code = riasec_service.top_code(profile_scores)
        meta = {
            "differentiation": riasec_service.differentiation(profile_scores),
            "consistency": riasec_service.consistency(code[:2]),
            "aversion": aversion_counts,
        }
        strengths, weaknesses = riasec_service.strengths_weaknesses(profile_scores, aversion_counts, counts)
        plan = riasec_service.development_plan(code, weaknesses, aversion_counts, counts)

        matched = await riasec_service.matched_careers(code, db)
        careers = [_career_dict(d, score) for d, score in matched]

    bf_raw = await bigfive_service.raw_scores(assessment_id, db, age_group)
    bf_counts = await bigfive_service.question_counts(db, age_group)
    bigfive_scores = bigfive_service.normalize(bf_raw, bf_counts)

    bf_facet_raw = await bigfive_service.facet_raw(assessment_id, db, age_group)
    bf_facet_counts = await bigfive_service.facet_counts(db, age_group)
    bf_facet_norm = bigfive_service.facet_normalize(bf_facet_raw, bf_facet_counts)
    thinking_style = thinking_style_service.compute(bf_facet_norm)

    personality_highlights = strength_phrases(bigfive_scores)
    personality_profile, personality_notes = bigfive_content.build_personality_profile(bigfive_scores)

    # Junior/middle answer the Harter-format pairs instead of the 3-way
    # MOST/LEAST triplets (senior) — different tables/scoring, same shape.
    if age_group in (AgeGroup.junior, AgeGroup.middle):
        mot_scores = await motivation_pair_service.raw_scores(assessment_id, db)
    else:
        mot_scores = await motivation_service.raw_scores(assessment_id, db)
    mot_top = motivation_service.top_categories(mot_scores)
    mot_highlights = motivation_highlight_phrases(mot_top)

    template_summary = _build_junior_summary(code) if age_group == AgeGroup.junior else _build_summary(code)
    ai_summary = await _generate_ai_summary(
        profile, assessment.goal.value, code, strengths, careers, artifacts,
        personality_highlights, mot_highlights,
    )
    summary = ai_summary or template_summary

    analysis = AnalysisResult(
        assessment_id=assessment_id,
        summary=summary,
        profile=profile_scores,
        code=code,
        meta=meta,
        careers=careers,
        strengths=strengths,
        weaknesses=weaknesses,
        development_plan=plan,
        big_five=bigfive_scores,
        thinking_style=thinking_style,
        personality_highlights=personality_highlights,
        personality_profile=personality_profile,
        personality_notes=personality_notes,
        motivation=mot_scores,
        motivation_top=mot_top,
        motivation_highlights=mot_highlights,
    )
    db.add(analysis)
    if assessment.status != AssessmentStatus.completed:
        # Same transaction as the AnalysisResult insert below — either both
        # land or neither does, so a completed-without-a-report assessment
        # can no longer exist.
        assessment.status = AssessmentStatus.completed
        assessment.completed_at = datetime.now(timezone.utc)
    try:
        await db.commit()
        await db.refresh(analysis)
    except IntegrityError:
        await db.rollback()
        existing_result = await db.execute(
            select(AnalysisResult).where(AnalysisResult.assessment_id == assessment_id)
        )
        analysis = existing_result.scalar_one()

    response = AnalysisResultResponse.model_validate(analysis)
    await redis.setex(cache_key, CACHE_TTL, response.model_dump_json())
    return response


async def get_report(
    assessment_id: uuid.UUID, db: AsyncSession
) -> AnalysisResultResponse | None:
    cache_key = f"report:{assessment_id}"
    redis = _get_redis()

    cached = await redis.get(cache_key)
    if cached:
        return AnalysisResultResponse.model_validate(json.loads(cached))

    result = await db.execute(
        select(AnalysisResult).where(AnalysisResult.assessment_id == assessment_id)
    )
    analysis = result.scalar_one_or_none()
    if analysis is None:
        return None
    response = AnalysisResultResponse.model_validate(analysis)
    await redis.setex(cache_key, CACHE_TTL, response.model_dump_json())
    return response
