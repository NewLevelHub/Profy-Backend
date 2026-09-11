"""Direction-fit inquiry service: AI probing questions about a direction + verdict.

middle/senior only. Questions are cached in Redis so the verdict step can rebuild
the exact Q&A from the answer indices. No template fallback — the whole feature is
AI, so failures surface as HTTP 503.
"""
import uuid

import redis.asyncio as aioredis
from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.errors import AppError
from app.models.direction_inquiry import DirectionInquiry
from app.prompts import direction_inquiry as prompt
from app.schemas.direction_inquiry import (
    DirectionQuestion,
    DirectionQuestionsResponse,
    DirectionVerdictResponse,
)
from app.schemas.student_context import StudentContext
from app.services import direction_service, llm_client
from app.services.riasec_content import likert_labels
from app.services.student_context import build_student_context

CACHE_TTL = 60 * 60  # 1 hour

_redis: aioredis.Redis | None = None

_AI_UNAVAILABLE = AppError(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    error_code="ai_unavailable",
    detail="ИИ временно недоступен, попробуй ещё раз",
)


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def _questions_key(assessment_id: uuid.UUID, slug: str) -> str:
    return f"dq:{assessment_id}:{slug}"


async def _load_context_and_direction(
    assessment_id: uuid.UUID, slug: str, db: AsyncSession
) -> tuple[StudentContext, object]:
    context = await build_student_context(assessment_id, db)
    if context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    if context.age_group == "junior":
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="feature_requires_age_10",
            detail="Эта возможность доступна с 10 лет",
        )
    if slug not in {d.slug for d in context.careers}:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="direction_not_in_results",
            detail="Это направление не входит в твои результаты",
        )
    direction = await direction_service.get_direction_by_slug(slug, db)
    if direction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Direction not found")
    return context, direction


async def generate_questions(
    assessment_id: uuid.UUID, slug: str, db: AsyncSession
) -> DirectionQuestionsResponse:
    if not llm_client.is_enabled():
        raise _AI_UNAVAILABLE

    redis = _get_redis()
    key = _questions_key(assessment_id, slug)
    cached = await redis.get(key)
    if cached:
        return DirectionQuestionsResponse.model_validate_json(cached)

    context, direction = await _load_context_and_direction(assessment_id, slug, db)

    messages = prompt.build_questions_messages(context, direction)
    try:
        raw = await llm_client.complete_json(messages, prompt.QUESTIONS_SCHEMA, "direction_questions")
        questions = [DirectionQuestion.model_validate(q) for q in raw.get("questions", [])]
    except (llm_client.LLMError, ValidationError, TypeError):
        raise _AI_UNAVAILABLE

    if not questions:
        raise _AI_UNAVAILABLE

    response = DirectionQuestionsResponse(
        direction_slug=slug,
        direction_name=direction.name,
        scale=likert_labels(),
        questions=questions,
    )
    await redis.setex(key, CACHE_TTL, response.model_dump_json())
    return response


async def build_verdict(
    assessment_id: uuid.UUID, slug: str, answers: list[int], db: AsyncSession
) -> DirectionVerdictResponse:
    if not llm_client.is_enabled():
        raise _AI_UNAVAILABLE

    redis = _get_redis()
    cached = await redis.get(_questions_key(assessment_id, slug))
    if not cached:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="inquiry_questions_not_generated",
            detail="Сначала получи вопросы по направлению",
        )
    questions = DirectionQuestionsResponse.model_validate_json(cached).questions

    if len(answers) != len(questions):
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="inquiry_answer_count_mismatch",
            detail="Число ответов не совпадает с числом вопросов",
        )
    if any(a < 0 or a >= len(likert_labels()) for a in answers):
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="inquiry_answer_invalid",
            detail="Некорректный ответ",
        )

    context, direction = await _load_context_and_direction(assessment_id, slug, db)

    qa = [{"q": q.text, "answer": likert_labels()[answers[i]]} for i, q in enumerate(questions)]
    messages = prompt.build_verdict_messages(context, direction, qa)
    try:
        raw = await llm_client.complete_json(messages, prompt.VERDICT_SCHEMA, "direction_verdict")
    except (llm_client.LLMError, TypeError):
        raise _AI_UNAVAILABLE

    try:
        verdict = DirectionVerdictResponse(
            direction_slug=slug,
            readiness=raw["readiness"],
            fit_summary=raw["fit_summary"],
            note=raw["note"],
        )
    except (KeyError, ValidationError):
        raise _AI_UNAVAILABLE

    await _save_inquiry(assessment_id, slug, questions, answers, verdict, db)
    return verdict


async def _save_inquiry(
    assessment_id: uuid.UUID,
    slug: str,
    questions: list[DirectionQuestion],
    answers: list[int],
    verdict: DirectionVerdictResponse,
    db: AsyncSession,
) -> None:
    """Persist the inquiry so the direction roadmap can build on it.

    Re-taking the inquiry for the same direction overwrites the previous run."""
    existing = (
        await db.execute(
            select(DirectionInquiry).where(
                DirectionInquiry.assessment_id == assessment_id,
                DirectionInquiry.direction_slug == slug,
            )
        )
    ).scalar_one_or_none()

    questions_data = [q.model_dump() for q in questions]
    if existing is None:
        db.add(
            DirectionInquiry(
                assessment_id=assessment_id,
                direction_slug=slug,
                questions=questions_data,
                answers=answers,
                readiness=verdict.readiness,
                fit_summary=verdict.fit_summary,
                note=verdict.note,
            )
        )
    else:
        existing.questions = questions_data
        existing.answers = answers
        existing.readiness = verdict.readiness
        existing.fit_summary = verdict.fit_summary
        existing.note = verdict.note
    await db.commit()


async def get_inquiry(
    assessment_id: uuid.UUID, slug: str, db: AsyncSession
) -> DirectionInquiry | None:
    return (
        await db.execute(
            select(DirectionInquiry).where(
                DirectionInquiry.assessment_id == assessment_id,
                DirectionInquiry.direction_slug == slug,
            )
        )
    ).scalar_one_or_none()
