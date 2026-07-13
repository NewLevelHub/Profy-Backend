"""Template-based roadmap generation. Interface is LLM-ready: swap build_roadmap body only."""

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass

import redis.asyncio as aioredis
from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.analysis_result import AnalysisResult
from app.models.artifact import Artifact
from app.models.assessment import Assessment, AssessmentGoal
from app.models.profile import Profile
from app.models.program import Program
from app.models.roadmap import Roadmap
from app.prompts import roadmap as roadmap_prompt
from app.schemas.roadmap import RoadmapMilestone, RoadmapResponse, RoadmapTask
from app.schemas.student_context import StudentContext
from app.services import assessment_service, llm_client
from app.services.gap_analysis_service import GapAnalysisResult, analyze_gap
from app.services.student_context import build_student_context

logger = logging.getLogger(__name__)

CACHE_TTL = 60 * 60 * 24  # 24 hours

_redis: aioredis.Redis | None = None

HORIZONS = ["month_1", "months_3", "months_6", "year_1", "until_goal"]


@dataclass
class _DirectionSummary:
    name: str
    slug: str
    first_steps: list[str]
    skills_needed: list[str]
    professions: list[str]


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def _cache_key(assessment_id: uuid.UUID, program_id: uuid.UUID | None) -> str:
    raw = f"{assessment_id}:{program_id or ''}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:24]
    return f"roadmap:{h}"


def _parse_directions(directions_jsonb: list) -> list[_DirectionSummary]:
    result = []
    for d in directions_jsonb:
        result.append(_DirectionSummary(
            name=d.get("name", ""),
            slug=d.get("slug", ""),
            first_steps=d.get("first_steps", []),
            skills_needed=d.get("skills_needed", []),
            professions=d.get("professions", []),
        ))
    return result


# ─── Template builders per scenario ────────────────────────────────────────────

def _build_explore(directions: list[_DirectionSummary]) -> list[RoadmapMilestone]:
    top = directions[:3]
    dir_names = [d.name for d in top] or ["интересующей сфере"]

    return [
        RoadmapMilestone(
            horizon="month_1",
            title="Первый шаг: исследование возможностей",
            tasks=[
                RoadmapTask(text=f"Узнай подробнее о направлении «{dir_names[0]}»: посмотри видео и статьи", category="explore", priority=1),
                RoadmapTask(text=f"Изучи, чем занимаются люди в сфере «{dir_names[1] if len(dir_names) > 1 else dir_names[0]}»", category="explore", priority=2),
                RoadmapTask(text="Найди один онлайн-курс по интересной теме и пройди первый урок", category="explore", priority=3),
            ],
        ),
        RoadmapMilestone(
            horizon="months_3",
            title="Попробовать что-то руками",
            tasks=[
                RoadmapTask(text=f"Запишись на пробный урок или кружок по направлению «{dir_names[0]}»", category="explore", priority=1),
                RoadmapTask(text="Посети одно тематическое мероприятие, фестиваль или открытый урок", category="explore", priority=2),
                RoadmapTask(text="Поговори с 1–2 людьми, которые работают в понравившейся тебе сфере", category="explore", priority=3),
            ],
        ),
        RoadmapMilestone(
            horizon="months_6",
            title="Углубиться в понравившееся",
            tasks=[
                RoadmapTask(text="Выбери 1–2 направления и занимайся ими регулярно (раз в неделю)", category="explore", priority=1),
                RoadmapTask(text="Найди наставника или ментора в выбранной сфере", category="explore", priority=2),
                RoadmapTask(text="Создай небольшой учебный проект или прими участие в конкурсе", category="explore", priority=3),
            ],
        ),
        RoadmapMilestone(
            horizon="year_1",
            title="Сделать осознанный выбор",
            tasks=[
                RoadmapTask(text="Определись с 1 основным направлением для дальнейшего развития", category="explore", priority=1),
                RoadmapTask(text="Составь список навыков, которые хочешь развить в этой сфере", category="planning", priority=2),
                RoadmapTask(text="Найди профессиональное сообщество онлайн или офлайн", category="explore", priority=3),
            ],
        ),
        RoadmapMilestone(
            horizon="until_goal",
            title="Сформировать чёткое видение будущего",
            tasks=[
                RoadmapTask(text="Сформулируй свои профессиональные интересы и цели в письменном виде", category="planning", priority=1),
                RoadmapTask(text="Исследуй пути обучения и развития по выбранному направлению", category="planning", priority=2),
                RoadmapTask(text="Обсуди планы с родителями, учителями или школьным куратором", category="planning", priority=3),
            ],
        ),
    ]


def _build_profession(directions: list[_DirectionSummary]) -> list[RoadmapMilestone]:
    top = directions[0] if directions else None
    top_name = top.name if top else "выбранном направлении"
    first_skills = (top.skills_needed[:2] if top else []) or ["ключевым навыкам"]
    first_steps = (top.first_steps[:3] if top else []) or ["Изучи базовые материалы по направлению"]

    return [
        RoadmapMilestone(
            horizon="month_1",
            title="Изучить профессии по результатам",
            tasks=[
                RoadmapTask(text=f"Изучи профессии в сфере «{top_name}» и выбери 1–2 наиболее интересных", category="knowledge", priority=1),
                RoadmapTask(text=f"Посмотри «день из жизни» специалиста в «{top_name}»", category="knowledge", priority=2),
                RoadmapTask(text="Составь список навыков, необходимых для работы в этой сфере", category="knowledge", priority=3),
            ],
        ),
        RoadmapMilestone(
            horizon="months_3",
            title="Начать развивать ключевые навыки",
            tasks=[
                RoadmapTask(text=first_steps[0], category="skill", priority=1),
                RoadmapTask(text=f"Пройди онлайн-курс по {first_skills[0] if first_skills else 'базовым навыкам направления'}", category="skill", priority=2),
                RoadmapTask(text="Найди учебные задачи или мини-проекты для практики", category="skill", priority=3),
            ],
        ),
        RoadmapMilestone(
            horizon="months_6",
            title="Первый практический опыт",
            tasks=[
                RoadmapTask(text=f"Сделай первый учебный проект в сфере «{top_name}»", category="practice", priority=1),
                RoadmapTask(text="Ищи возможности для волонтёрства или стажировки по теме", category="practice", priority=2),
                RoadmapTask(text="Собери первое портфолио своих работ", category="portfolio", priority=3),
            ],
        ),
        RoadmapMilestone(
            horizon="year_1",
            title="Профессиональное позиционирование",
            tasks=[
                RoadmapTask(text="Дополни портфолио 2–3 значимыми проектами", category="portfolio", priority=1),
                RoadmapTask(text="Сформулируй карьерные цели на ближайшие 3–5 лет", category="career", priority=2),
                RoadmapTask(text="Пройди профессиональную консультацию или карьерное тестирование", category="career", priority=3),
            ],
        ),
        RoadmapMilestone(
            horizon="until_goal",
            title="Начало профессионального пути",
            tasks=[
                RoadmapTask(text="Подготовь резюме и начни поиск первой работы или практики", category="career", priority=1),
                RoadmapTask(text=f"Поступи на профессиональную программу обучения по направлению «{top_name}»", category="education", priority=2),
                RoadmapTask(text="Найди ментора в выбранной сфере для карьерной поддержки", category="career", priority=3),
            ],
        ),
    ]


def _build_university(directions: list[_DirectionSummary], gap: GapAnalysisResult | None) -> list[RoadmapMilestone]:
    # month_1: prioritise not_met requirements
    if gap and gap.not_met:
        month1_tasks = [
            RoadmapTask(
                text=f"Закрыть требование «{item.requirement}»: {item.comment}",
                category="requirement",
                priority=i + 1,
            )
            for i, item in enumerate(gap.not_met[:3])
        ]
    else:
        month1_tasks = [
            RoadmapTask(text="Изучи требования к поступлению в целевой университет", category="planning", priority=1),
            RoadmapTask(text="Составь список документов, необходимых для подачи заявки", category="documents", priority=2),
            RoadmapTask(text="Найди дедлайны подачи документов и запиши их", category="planning", priority=3),
        ]

    # months_3: work on in_progress requirements
    if gap and gap.in_progress:
        months3_tasks = [
            RoadmapTask(
                text=f"Продолжить работу над «{item.requirement}»: {item.comment}",
                category="requirement",
                priority=i + 1,
            )
            for i, item in enumerate(gap.in_progress[:3])
        ]
    else:
        months3_tasks = [
            RoadmapTask(text="Подготовься к сдаче вступительных экзаменов или тестов", category="exam", priority=1),
            RoadmapTask(text="Запишись на курсы подготовки к экзаменам (при необходимости)", category="exam", priority=2),
            RoadmapTask(text="Начни собирать портфолио достижений", category="portfolio", priority=3),
        ]

    return [
        RoadmapMilestone(
            horizon="month_1",
            title="Закрыть критические пробелы",
            tasks=month1_tasks,
        ),
        RoadmapMilestone(
            horizon="months_3",
            title="Устранить пробелы в процессе",
            tasks=months3_tasks,
        ),
        RoadmapMilestone(
            horizon="months_6",
            title="Подготовить документы к поступлению",
            tasks=[
                RoadmapTask(text="Собери все необходимые документы для подачи заявки", category="documents", priority=1),
                RoadmapTask(text="Напиши мотивационное письмо или вступительное эссе", category="documents", priority=2),
                RoadmapTask(text="Проверь дедлайны подачи документов и расставь напоминания", category="planning", priority=3),
            ],
        ),
        RoadmapMilestone(
            horizon="year_1",
            title="Подать заявку",
            tasks=[
                RoadmapTask(text="Отправь заявку на поступление в университет", category="application", priority=1),
                RoadmapTask(text="Изучи возможности стипендий и грантов для поступающих", category="finance", priority=2),
                RoadmapTask(text="Подготовь 2–3 запасных варианта университетов", category="planning", priority=3),
            ],
        ),
        RoadmapMilestone(
            horizon="until_goal",
            title="Поступление",
            tasks=[
                RoadmapTask(text="Пройди вступительные испытания или собеседование", category="admission", priority=1),
                RoadmapTask(text="Подпиши оферт о зачислении", category="admission", priority=2),
                RoadmapTask(text="Оформи необходимые документы (виза, общежитие, регистрация)", category="admission", priority=3),
            ],
        ),
    ]


# ─── Public LLM-ready interface ─────────────────────────────────────────────────

def build_roadmap(
    profile: Profile,
    goal: str,
    matched_directions: list[_DirectionSummary],
    gap_analysis: GapAnalysisResult | None = None,
    program: Program | None = None,
) -> list[RoadmapMilestone]:
    """Deterministic template roadmap — the fallback when the LLM is off or fails.

    The AI path lives in `_build_roadmap_ai`; `generate_roadmap` tries it first."""
    if goal == AssessmentGoal.university:
        return _build_university(matched_directions, gap_analysis)
    if goal == AssessmentGoal.profession:
        return _build_profession(matched_directions)
    # explore and unsure ("Пока не знаю") share the exploratory roadmap
    return _build_explore(matched_directions)


def _valid_milestones(milestones: list[RoadmapMilestone]) -> bool:
    """Structure guard: all 5 horizons present exactly once, each with tasks."""
    if len(milestones) != len(HORIZONS):
        return False
    if {m.horizon for m in milestones} != set(HORIZONS):
        return False
    return all(m.tasks for m in milestones)


async def _build_roadmap_ai(
    context: StudentContext | None,
) -> list[RoadmapMilestone] | None:
    """LLM roadmap. Returns None (→ template fallback) if disabled or anything fails."""
    if context is None or not llm_client.is_enabled():
        return None
    try:
        messages = roadmap_prompt.build_messages(context)
        raw = await llm_client.complete_json(
            messages, roadmap_prompt.ROADMAP_JSON_SCHEMA, "roadmap"
        )
        milestones = [
            RoadmapMilestone.model_validate(m) for m in raw.get("milestones", [])
        ]
    except (llm_client.LLMError, ValidationError, TypeError) as exc:
        logger.warning("AI roadmap failed, using template: %s", exc)
        return None
    if not _valid_milestones(milestones):
        logger.warning("AI roadmap failed invariant check, using template")
        return None
    return milestones


# ─── Service layer (DB + cache) ─────────────────────────────────────────────────

async def generate_roadmap(
    assessment_id: uuid.UUID,
    program_id: uuid.UUID | None,
    db: AsyncSession,
) -> RoadmapResponse:
    redis = _get_redis()
    key = _cache_key(assessment_id, program_id)

    cached = await redis.get(key)
    if cached:
        return RoadmapResponse.model_validate(json.loads(cached))

    # Load assessment
    assessment_row = await db.execute(select(Assessment).where(Assessment.id == assessment_id))
    assessment = assessment_row.scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    # Load profile
    profile_row = await db.execute(select(Profile).where(Profile.id == assessment.profile_id))
    profile = profile_row.scalar_one_or_none()

    # Load matched directions from stored analysis result
    result_row = await db.execute(
        select(AnalysisResult).where(AnalysisResult.assessment_id == assessment_id)
    )
    analysis = result_row.scalar_one_or_none()
    directions_raw: list = analysis.directions if analysis else []
    directions = _parse_directions(directions_raw)

    # Gap analysis (university + program_id)
    gap: GapAnalysisResult | None = None
    program: Program | None = None
    if assessment.goal == AssessmentGoal.university and program_id:
        prog_row = await db.execute(select(Program).where(Program.id == program_id))
        program = prog_row.scalar_one_or_none()
        if program:
            artifacts_row = await db.execute(
                select(Artifact).where(Artifact.profile_id == assessment.profile_id)
            )
            artifacts = list(artifacts_row.scalars().all())
            scores = await assessment_service.get_total_scores(assessment_id, db)
            gap = analyze_gap(profile, artifacts, scores, program)

    # Full context bundle (profile + analysis + surfaced signals) for the LLM.
    context = await build_student_context(assessment_id, db)

    # Try the LLM first; fall back to deterministic templates on any failure.
    milestones = await _build_roadmap_ai(context)
    if milestones is None:
        milestones = build_roadmap(profile, assessment.goal, directions, gap, program)
    milestones_data = [m.model_dump() for m in milestones]

    # Upsert roadmap in DB
    existing_row = await db.execute(select(Roadmap).where(Roadmap.assessment_id == assessment_id))
    existing = existing_row.scalar_one_or_none()
    if existing:
        existing.goal = assessment.goal
        existing.milestones = milestones_data
        roadmap = existing
    else:
        roadmap = Roadmap(
            assessment_id=assessment_id,
            goal=assessment.goal,
            milestones=milestones_data,
        )
        db.add(roadmap)

    await db.commit()
    await db.refresh(roadmap)

    response = RoadmapResponse.model_validate(roadmap)
    await redis.setex(key, CACHE_TTL, response.model_dump_json())
    return response


async def get_roadmap(
    assessment_id: uuid.UUID,
    db: AsyncSession,
) -> RoadmapResponse | None:
    redis = _get_redis()
    key = _cache_key(assessment_id, None)

    cached = await redis.get(key)
    if cached:
        return RoadmapResponse.model_validate(json.loads(cached))

    row = await db.execute(select(Roadmap).where(Roadmap.assessment_id == assessment_id))
    roadmap = row.scalar_one_or_none()
    if roadmap is None:
        return None

    response = RoadmapResponse.model_validate(roadmap)
    await redis.setex(key, CACHE_TTL, response.model_dump_json())
    return response
