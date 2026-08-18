"""Template-based roadmap generation. Interface is LLM-ready: swap build_roadmap body only."""

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
from app.data import resource_catalog
from app.models.analysis_result import AnalysisResult
from app.models.artifact import Artifact
from app.models.assessment import Assessment, AssessmentGoal
from app.models.direction import Direction
from app.models.direction_roadmap import DirectionRoadmap
from app.models.profile import AgeGroup, Profile
from app.models.program import Program
from app.models.roadmap import Roadmap
from app.models.university import University
from app.prompts import direction_roadmap as direction_prompt
from app.prompts import roadmap as roadmap_prompt
from app.schemas.roadmap import (
    DIRECTION_HORIZONS,
    DirectionRoadmapResponse,
    DirectionStage,
    GrowthFocus,
    RecommendedPath,
    RoadmapMilestone,
    RoadmapResponse,
    RoadmapTarget,
    RoadmapTask,
    UniversityRequirement,
    UniversityTrack,
)
from app.schemas.student_context import StudentContext
from app.services import (
    assessment_service,
    assessment_shared,
    direction_inquiry_service,
    direction_service,
    llm_client,
)
from app.services import university_requirements as ureq
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
    # Plain, not hashed — a retake needs to invalidate every cached variant of
    # this assessment's goal roadmap (one per program_id ever requested), and
    # that's only possible via a pattern scan (see
    # assessment_shared.invalidate_goal_roadmap) if the assessment_id is
    # readable in the key, not buried inside a hash.
    #
    # Prefix is versioned (assessment_shared.ROADMAP_CACHE_KEY_PREFIX) so
    # bumping it makes every previously cached response (old prompt wording)
    # a cache miss on deploy without a manual redis-cli scan/flush.
    return f"{assessment_shared.ROADMAP_CACHE_KEY_PREFIX}:{assessment_id}:{program_id or 'none'}"


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

def _build_explore(
    directions: list[_DirectionSummary],
) -> tuple[list[RoadmapMilestone], list[RecommendedPath]]:
    """Template fallback for goal=explore/unsure — used when the LLM is off or
    fails. Mirrors the LLM prompt's portrait+path structure (see
    app/prompts/roadmap.py) as closely as a static template can: 1-2 leading
    directions from the top matched careers, tasks tagged by path from
    months_3 onward. Without the LLM there's no personalised why/future_benefit,
    so those are generic-but-named-to-the-direction rather than truly personal."""
    top = directions[:2]
    paths = [
        RecommendedPath(
            key=chr(ord("A") + i),
            label=d.name,
            why=f"По результатам теста направление «{d.name}» — один из твоих самых сильных откликов.",
            future_benefit=f"Развитие в «{d.name}» может привести к кружкам и конкурсам следующего уровня, а дальше — к профессиям в этой сфере.",
        )
        for i, d in enumerate(top)
    ] or [
        RecommendedPath(
            key="A",
            label="интересующей сфере",
            why="Пока по тесту не выделилось одно явное направление — начни с общей разведки интересов.",
            future_benefit="Это поможет нащупать, какая сфера откликается сильнее всего.",
        )
    ]
    single = len(paths) == 1

    def try_task(path: RecommendedPath, priority: int) -> RoadmapTask:
        return RoadmapTask(
            text=f"Узнай подробнее о направлении «{path.label}»: посмотри видео, статьи или пробное занятие",
            category="explore", priority=priority, path=None,
        )

    def deepen_task(path: RecommendedPath, priority: int) -> RoadmapTask:
        return RoadmapTask(
            text=f"Занимайся направлением «{path.label}» регулярно (раз в неделю) и сделай небольшой проект руками",
            category="skill", priority=priority, path=path.key,
        )

    def compete_task(path: RecommendedPath, priority: int) -> RoadmapTask:
        return RoadmapTask(
            text=f"Прими участие в конкурсе, соревновании или открытом показе по направлению «{path.label}»",
            category="portfolio", priority=priority, path=path.key,
        )

    # Every milestone must land in the 4-5 task band (same rule the LLM path is
    # held to, _valid_milestones) regardless of whether there are 1 or 2 paths —
    # so path-specific tasks are topped up with common (path=None) ones.
    month1_tasks = [try_task(p, i + 1) for i, p in enumerate(paths)]
    month1_tasks.append(
        RoadmapTask(text="Сравни впечатления от попробованного и запиши, что понравилось больше", category="planning", priority=len(month1_tasks) + 1, path=None)
    )
    month1_tasks.append(
        RoadmapTask(text="Обсуди с родителями или учителем, что из попробованного откликнулось сильнее", category="planning", priority=len(month1_tasks) + 1, path=None)
    )
    if single:
        month1_tasks.append(
            RoadmapTask(text="Найди ещё один формат по этому же направлению (видео другого автора, другой кружок) и сравни впечатления", category="explore", priority=len(month1_tasks) + 1, path=None)
        )

    decide_text = (
        f"Определись: продолжать «{paths[0].label}» или пробовать несколько направлений параллельно"
        if single
        else f"Определись: продолжать одно направление ({' или '.join(p.label for p in paths)}) или оба параллельно"
    )
    months3_tasks = [RoadmapTask(text=decide_text, category="planning", priority=1, path=None)]
    months3_tasks += [
        RoadmapTask(
            text=f"Найди регулярный формат (кружок, секция, курс) по направлению «{p.label}» и сходи на первое занятие",
            category="explore", priority=i + 2, path=p.key,
        )
        for i, p in enumerate(paths)
    ]
    months3_tasks.append(
        RoadmapTask(text="Попробуй сделать что-то своё на основе того, что уже пробовал, а не по инструкции", category="skill", priority=len(months3_tasks) + 1, path=None)
    )
    if single:
        months3_tasks.append(
            RoadmapTask(text="Уточни у руководителя кружка/секции, что нужно для более серьёзных занятий дальше", category="planning", priority=len(months3_tasks) + 1, path=None)
        )

    months6_tasks = [deepen_task(p, i + 1) for i, p in enumerate(paths)]
    months6_tasks.append(
        RoadmapTask(text="Найди наставника или ментора в выбранной сфере", category="explore", priority=len(months6_tasks) + 1, path=None)
    )
    months6_tasks.append(
        RoadmapTask(text="Покажи то, что сделал, кому-то ещё (семье, друзьям, руководителю кружка) и собери отклик", category="practice", priority=len(months6_tasks) + 1, path=None)
    )
    if single:
        months6_tasks.append(
            RoadmapTask(text="Запиши, что даётся легко, а что пока сложно в этом направлении", category="planning", priority=len(months6_tasks) + 1, path=None)
        )

    year1_tasks = [compete_task(p, i + 1) for i, p in enumerate(paths)]
    year1_tasks.append(
        RoadmapTask(text="Составь список навыков, которые хочешь развить дальше в этой сфере", category="planning", priority=len(year1_tasks) + 1, path=None)
    )
    year1_tasks.append(
        RoadmapTask(text="Найди профессиональное сообщество (онлайн или офлайн) по этой сфере", category="explore", priority=len(year1_tasks) + 1, path=None)
    )
    if single:
        year1_tasks.append(
            RoadmapTask(text="Обсуди с наставником или родителями цели на следующий год", category="planning", priority=len(year1_tasks) + 1, path=None)
        )

    until_goal_tasks = [
        RoadmapTask(text="Сформулируй свои интересы и цели в этой сфере в письменном виде", category="planning", priority=1, path=None),
        RoadmapTask(text="Исследуй пути дальнейшего обучения и развития по выбранному направлению", category="planning", priority=2, path=None),
        RoadmapTask(text="Обсуди планы с родителями, учителями или школьным куратором", category="planning", priority=3, path=None),
        RoadmapTask(text="Составь план на следующий год с конкретными шагами и датами", category="planning", priority=4, path=None),
    ]

    milestones = [
        RoadmapMilestone(
            horizon="month_1",
            title="Первые пробы по ведущим направлениям",
            outcome="Понимание своих интересов и первые впечатления от каждого предложенного направления.",
            tasks=month1_tasks,
        ),
        RoadmapMilestone(
            horizon="months_3",
            title="Решение и начало веток",
            outcome="Осознанное решение — одно направление или оба — и первый регулярный формат занятий.",
            tasks=months3_tasks,
        ),
        RoadmapMilestone(
            horizon="months_6",
            title="Углубление в выбранное направление",
            outcome="Регулярные занятия и первый самостоятельный проект в выбранном направлении.",
            tasks=months6_tasks,
        ),
        RoadmapMilestone(
            horizon="year_1",
            title="Предъявление результата",
            outcome="Первый публичный результат — участие в конкурсе, соревновании или показе.",
            tasks=year1_tasks,
        ),
        RoadmapMilestone(
            horizon="until_goal",
            title="Сформировать чёткое видение будущего",
            outcome="Чёткое представление о будущей сфере и путях обучения.",
            tasks=until_goal_tasks,
        ),
    ]
    return milestones, paths


def _build_profession(directions: list[_DirectionSummary]) -> list[RoadmapMilestone]:
    top = directions[0] if directions else None
    top_name = top.name if top else "выбранном направлении"
    first_skills = (top.skills_needed[:2] if top else []) or ["ключевым навыкам"]
    first_steps = (top.first_steps[:3] if top else []) or ["Изучи базовые материалы по направлению"]

    return [
        RoadmapMilestone(
            horizon="month_1",
            title="Изучить профессии по результатам",
            outcome="Сформированное понимание ключевых профессий в выбранной сфере.",
            tasks=[
                RoadmapTask(text=f"Изучи профессии в сфере «{top_name}» и выбери 1–2 наиболее интересных", category="knowledge", priority=1),
                RoadmapTask(text=f"Посмотри «день из жизни» специалиста в «{top_name}»", category="knowledge", priority=2),
                RoadmapTask(text="Составь список навыков, необходимых для работы в этой сфере", category="knowledge", priority=3),
            ],
        ),
        RoadmapMilestone(
            horizon="months_3",
            title="Начать развивать ключевые навыки",
            outcome="Освоение базовых теоретических и практических навыков.",
            tasks=[
                RoadmapTask(text=first_steps[0], category="skill", priority=1),
                RoadmapTask(text=f"Пройди онлайн-курс по {first_skills[0] if first_skills else 'базовым навыкам направления'}", category="skill", priority=2),
                RoadmapTask(text="Найди учебные задачи или мини-проекты для практики", category="skill", priority=3),
            ],
        ),
        RoadmapMilestone(
            horizon="months_6",
            title="Первый практический опыт",
            outcome="Создание первого учебного проекта для портфолио.",
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
            outcome="План закрытия критических пробелов для поступления.",
            tasks=month1_tasks,
        ),
        RoadmapMilestone(
            horizon="months_3",
            title="Устранить пробелы в процессе",
            outcome="Устранение пробелов в знаниях и навыках для вуза.",
            tasks=months3_tasks,
        ),
        RoadmapMilestone(
            horizon="months_6",
            title="Подготовить документы к поступлению",
            outcome="Собранный комплект документов и готовое эссе.",
            tasks=[
                RoadmapTask(text="Собери все необходимые документы для подачи заявки", category="documents", priority=1),
                RoadmapTask(text="Напиши мотивационное письмо или вступительное эссе", category="documents", priority=2),
                RoadmapTask(text="Проверь дедлайны подачи документов и расставь напоминания", category="planning", priority=3),
            ],
        ),
        RoadmapMilestone(
            horizon="year_1",
            title="Подать заявку",
            outcome="Поданные заявления в выбранные вузы.",
            tasks=[
                RoadmapTask(text="Отправь заявку на поступление в университет", category="application", priority=1),
                RoadmapTask(text="Изучи возможности стипендий и грантов для поступающих", category="finance", priority=2),
                RoadmapTask(text="Подготовь 2–3 запасных варианта университетов", category="planning", priority=3),
            ],
        ),
        RoadmapMilestone(
            horizon="until_goal",
            title="Поступление",
            outcome="Успешное прохождение испытаний и зачисление.",
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
) -> tuple[list[RoadmapMilestone], str, list[RecommendedPath]]:
    """Deterministic template roadmap — the fallback when the LLM is off or fails.

    The AI path lives in `_build_roadmap_ai`; `generate_roadmap` tries it first."""
    if goal == AssessmentGoal.university:
        milestones = _build_university(matched_directions, gap_analysis)
        focus = "Этот план сфокусирован на подготовке к поступлению в вуз: закрытии академических пробелов, сборе необходимых документов, подготовке к экзаменам и успешной подаче заявления."
        return milestones, focus, []
    if goal == AssessmentGoal.profession:
        milestones = _build_profession(matched_directions)
        focus = "План ориентирован на развитие практических навыков в выбранной профессии, создание первого портфолио проектов и подготовку к старту в профессиональной среде."
        return milestones, focus, []
    # explore and unsure ("Пока не знаю") share the exploratory roadmap
    milestones, recommended_paths = _build_explore(matched_directions)
    focus = "Судя по твоим ответам, у тебя есть явные интересы и сильные стороны — этот план поможет попробовать ведущие направления на практике и сделать осознанный выбор без давления и спешки."
    return milestones, focus, recommended_paths


_MIN_TASKS_PER_MILESTONE = 4
_MAX_TASKS_PER_MILESTONE = 5


_MAX_RECOMMENDED_PATHS = 2
_EXPLORE_GOALS = {"explore", "unsure"}


def _valid_milestones(milestones: list[RoadmapMilestone]) -> bool:
    """Structure guard: all 5 horizons present exactly once, each with a dense,
    bounded set of tasks. Too few and a horizon doesn't fill its real time
    budget (a month that's "watch one video" isn't a month); too many and it
    paralyses — TZ §23.6 caps a stage at 5 tasks."""
    if len(milestones) != len(HORIZONS):
        return False
    if {m.horizon for m in milestones} != set(HORIZONS):
        return False
    return all(
        _MIN_TASKS_PER_MILESTONE <= len(m.tasks) <= _MAX_TASKS_PER_MILESTONE and bool(m.outcome)
        for m in milestones
    )


def _valid_explore_paths(
    goal: str, milestones: list[RoadmapMilestone], recommended_paths: list[RecommendedPath]
) -> bool:
    """For goal in (explore, unsure): recommended_paths must name 1-2 grounded
    leading directions, month_1 tasks must stay common (decision not made
    yet), and later horizons must actually use the path(s) named — otherwise
    recommended_paths is just decoration nobody's tasks refer to.

    For every other goal (profession/university) this is a no-op: the goal
    already has a single confirmed direction, branching doesn't apply."""
    if goal not in _EXPLORE_GOALS:
        return True
    if not (1 <= len(recommended_paths) <= _MAX_RECOMMENDED_PATHS):
        return False
    if not all(p.why and p.future_benefit for p in recommended_paths):
        return False
    valid_keys = {p.key for p in recommended_paths}

    by_horizon = {m.horizon: m for m in milestones}
    month1 = by_horizon.get("month_1")
    if month1 is not None and any(t.path is not None for t in month1.tasks):
        return False

    for horizon in ("months_3", "months_6"):
        stage = by_horizon.get(horizon)
        if stage is None:
            continue
        used_paths = {t.path for t in stage.tasks if t.path is not None}
        if len(valid_keys) > 1 and not used_paths:
            return False
        if not used_paths.issubset(valid_keys):
            return False
    return True


_MAX_ROADMAP_ATTEMPTS = 2  # 1 initial + 1 corrective retry


async def _build_roadmap_ai(
    context: StudentContext | None,
) -> tuple[list[RoadmapMilestone], str, list[RecommendedPath]] | None:
    """LLM roadmap. Returns None (→ template fallback) if disabled or anything fails.

    Retries once on an invariant miss (density/structure) before giving up —
    same pattern as `_generate_plan` for the direction roadmap: a corrective
    pass is cheaper than falling straight back to the much thinner template."""
    if context is None or not llm_client.is_enabled():
        return None

    messages = roadmap_prompt.build_messages(context)
    for attempt in range(1, _MAX_ROADMAP_ATTEMPTS + 1):
        try:
            raw = await llm_client.complete_json(
                messages,
                roadmap_prompt.ROADMAP_JSON_SCHEMA,
                "roadmap",
                timeout=settings.LLM_ROADMAP_TIMEOUT,
                max_tokens=settings.LLM_ROADMAP_MAX_TOKENS,
                model=settings.LLM_ROADMAP_MODEL,
            )
            milestones = [
                RoadmapMilestone.model_validate(m) for m in raw.get("milestones", [])
            ]
            focus_summary = raw.get("focus_summary", "")
            recommended_paths = [
                RecommendedPath.model_validate(p) for p in raw.get("recommended_paths", [])
            ]
        except (llm_client.LLMError, ValidationError, TypeError) as exc:
            logger.warning("AI roadmap failed, using template: %s", exc)
            return None

        if (
            _valid_milestones(milestones)
            and bool(focus_summary)
            and _valid_explore_paths(context.goal, milestones, recommended_paths)
        ):
            return milestones, focus_summary, recommended_paths

        logger.warning(
            "AI roadmap failed invariant check (attempt %s/%s)",
            attempt, _MAX_ROADMAP_ATTEMPTS,
        )
        messages = [*messages, roadmap_prompt.RETRY_HINT]

    return None


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
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    # ТЗ §10.3 soft downgrade (middle + "university" -> "profession") must hold
    # for generation too, not just for the goal-overlay banner — see
    # `assessment_shared.get_effective_goal`. Every branch below uses this,
    # never the raw `assessment.goal`.
    effective_goal = assessment_shared.get_effective_goal(profile.age_group, assessment.goal)

    # Load matched directions from stored analysis result
    result_row = await db.execute(
        select(AnalysisResult).where(AnalysisResult.assessment_id == assessment_id)
    )
    analysis = result_row.scalar_one_or_none()
    directions_raw: list = analysis.careers if analysis else []
    directions = _parse_directions(directions_raw)

    # Gap analysis (university + program_id)
    gap: GapAnalysisResult | None = None
    program: Program | None = None
    if effective_goal == AssessmentGoal.university and program_id:
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
    ai_res = await _build_roadmap_ai(context)
    if ai_res is not None:
        milestones, focus_summary, recommended_paths = ai_res
    else:
        milestones, focus_summary, recommended_paths = build_roadmap(
            profile, effective_goal, directions, gap, program
        )
    milestones_data = [m.model_dump() for m in milestones]
    recommended_paths_data = [p.model_dump() for p in recommended_paths]

    # Deterministic, non-LLM catalogue match — see app/data/resource_catalog.py.
    # Prefer the direction the student actually confirmed/selected (set once
    # a direction roadmap is generated, see _upsert_direction_roadmap) over
    # the raw #1 RIASEC match: for profession/university goals `directions[0]`
    # is just the top test-score match and can easily be a different career
    # than the one the roadmap is actually about (e.g. "Финансовый аналитик"
    # outscoring the nursing direction the student picked) — the confirmed
    # slug is a much stronger signal when it exists.
    match_direction = next(
        (d for d in directions if d.slug == assessment.selected_direction_slug), None
    ) or (directions[0] if directions else None)
    category = (
        resource_catalog.match_category(match_direction.name, " ".join(match_direction.skills_needed))
        if match_direction
        else None
    )
    additional_resources_data = resource_catalog.resources_for_category(category)

    # Upsert roadmap in DB
    existing_row = await db.execute(select(Roadmap).where(Roadmap.assessment_id == assessment_id))
    existing = existing_row.scalar_one_or_none()
    if existing:
        existing.goal = effective_goal
        existing.focus_summary = focus_summary
        existing.milestones = milestones_data
        existing.recommended_paths = recommended_paths_data
        existing.additional_resources = additional_resources_data
        roadmap = existing
    else:
        roadmap = Roadmap(
            assessment_id=assessment_id,
            goal=effective_goal,
            focus_summary=focus_summary,
            milestones=milestones_data,
            recommended_paths=recommended_paths_data,
            additional_resources=additional_resources_data,
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


# ─── Direction roadmap (AI-only, no template fallback) ──────────────────────────

_AI_UNAVAILABLE = HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    detail="ИИ временно недоступен, попробуй ещё раз",
)


@dataclass
class _DirectionPlan:
    """The LLM's plan, validated — everything the roadmap row needs."""

    target: RoadmapTarget
    growth_focus: GrowthFocus
    stages: list[DirectionStage]
    skills_to_build: list[str]
    subjects_to_focus: list[str]
    university_track: UniversityTrack
    # Backend-populated, never the model's decision — see _university_requirements_for.
    # Empty for every goal except "university".
    university_requirements: list[UniversityRequirement]


def direction_cache_key(
    assessment_id: uuid.UUID, slug: str, program_id: uuid.UUID | None = None
) -> str:
    """`program_id` only matters for the generate-by-program path: without it,
    regenerating the same direction under a *different* program within the
    24h TTL would silently return the previous program's cached plan. Plain
    GET (`get_direction_roadmap`) intentionally omits it — it just reads
    whatever the single upserted DB row for this direction currently is."""
    prefix = assessment_shared.DIRECTION_ROADMAP_CACHE_KEY_PREFIX
    if program_id is None:
        return f"{prefix}:{assessment_id}:{slug}"
    return f"{prefix}:{assessment_id}:{slug}:{program_id}"


# ─── University facts (backend-only; goal == "university" only) ─────────────────
#
# The requirements->UniversityRequirement mapping itself lives in
# app/services/university_requirements.py — shared with the plain
# program-detail screen (ProgramDetail.requirements_summary) so both surfaces
# render the exact same clean facts instead of each parsing the raw JSON its
# own way (see that module's docstring for the two seed-source shapes).


async def _program_and_university(
    program_id: uuid.UUID, db: AsyncSession
) -> tuple[Program, University] | None:
    row = (
        await db.execute(
            select(Program, University)
            .join(University, Program.university_id == University.id)
            .where(Program.id == program_id)
        )
    ).first()
    return (row[0], row[1]) if row else None


async def _university_requirements_for(slug: str, db: AsyncSession) -> list[UniversityRequirement]:
    """Real Program/University facts for this direction — never asked of the LLM.
    Only called for goal == "university"; every other goal gets [].

    Matches via the `program_directions` M2M table (direct hand-mapped link
    between a Program and the Direction(s) it prepares someone for) — the
    old `Program.direction_slug` category-bridge field was dropped in
    migration 0033 for producing false matches, and the JSONB
    `profession_slugs` array that replaced it was itself later replaced by
    a real FK-backed join table (migration 5f7925c25fbb); see
    `app/services/university_service.py` for the same join pattern."""
    rows = (
        await db.execute(
            select(Program, University)
            .join(University, Program.university_id == University.id)
            .join(Program.directions)
            .where(Direction.slug == slug)
        )
    ).all()
    return [ureq.map_program_requirement(program, university) for program, university in rows]


_MIN_STEPS_PER_STAGE = 3


def _valid_stages(stages: list[DirectionStage]) -> bool:
    """Structure guard: all 4 horizons exactly once, every stage has enough steps,
    and no stage drops either kind of work — that would defeat the point of the plan.

    An `integration` step counts as both: it is, by definition, work that needs the
    profile skill and the growth area at the same time. Demanding a separate
    `profile` step on top of it would reject perfectly good months_9 stages."""
    if len(stages) != len(DIRECTION_HORIZONS):
        return False
    if {s.horizon for s in stages} != set(DIRECTION_HORIZONS):
        return False
    for stage in stages:
        if len(stage.steps) < _MIN_STEPS_PER_STAGE:
            return False
        tracks = {step.track for step in stage.steps}
        if not tracks & {"profile", "integration"}:
            return False
        if not tracks & {"growth", "integration"}:
            return False
        # Every stage must break subjects down into concrete, grade-tied topics
        # (not just the root-level subjects_to_focus name list) — this is the
        # whole point of the subject_focus field, see app/schemas/roadmap.py.
        if not stage.subject_focus:
            return False
        if any(not item.topics for item in stage.subject_focus):
            return False
    return True


def _valid_plan(plan: "_DirectionPlan") -> bool:
    """Structure guard for the whole plan, not just the stages — a technically
    well-shaped stage list is still a broken plan if `subjects_to_focus` or
    `skills_to_build` came back empty: the student is left with steps but no
    answer to "what school subjects should I actually focus on", which is
    exactly the concrete, checkable payoff this feature exists for."""
    if not _valid_stages(plan.stages):
        return False
    return bool(plan.subjects_to_focus) and bool(plan.skills_to_build)


# Product decision (2026-08-17): skip the AI-inquiry precondition for every
# goal, not just "university" — a student now goes straight from a direction
# card to the plan. The inquiry feature itself (service/router/model/frontend
# page) is NOT deleted, only unlinked from this entry point: flip this back to
# True to require it again without touching anything else.
_INQUIRY_REQUIRED = False


async def _require_direction_roadmap_access(
    assessment_id: uuid.UUID, slug: str, db: AsyncSession
) -> tuple[Assessment, object]:
    """Enforce the feature's preconditions: not junior, and — while
    `_INQUIRY_REQUIRED` is on, and for every goal except "university" — the
    student has actually gone through the AI inquiry for this direction.

    University always skips the inquiry: picking a specific program and
    seeing its gap-analysis (see `generate_direction_roadmap_for_program`)
    already is the "does this fit me" check for that scenario, so requiring
    the generic inquiry on top would be redundant friction, not extra safety.

    `university` used to be excluded here entirely (it had its own, poorer
    branch — see goal roadmap's `_build_university`). It now goes through the
    same direction-roadmap pipeline as every other goal; the only thing that
    still varies by goal is the prompt emphasis and the backend-populated
    `university_requirements` (see `_university_requirements_for`)."""
    assessment = (
        await db.execute(select(Assessment).where(Assessment.id == assessment_id))
    ).scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    profile = (
        await db.execute(select(Profile).where(Profile.id == assessment.profile_id))
    ).scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    if profile.age_group == AgeGroup.junior:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Эта возможность доступна с 10 лет",
        )

    if _INQUIRY_REQUIRED:
        effective_goal = assessment_shared.get_effective_goal(profile.age_group, assessment.goal)
        if effective_goal != AssessmentGoal.university:
            inquiry = await direction_inquiry_service.get_inquiry(assessment_id, slug, db)
            if inquiry is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Сначала пройди опрос по этому направлению",
                )

    direction = await direction_service.get_direction_by_slug(slug, db)
    if direction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Direction not found")

    return assessment, direction


_MAX_PLAN_ATTEMPTS = 2  # 1 initial + 1 corrective retry


async def _generate_plan(
    context: StudentContext,
    direction,
    university_requirements: list[UniversityRequirement],
    gap: GapAnalysisResult | None = None,
) -> _DirectionPlan | None:
    """Ask the LLM for a plan, retrying once if it breaks the structural rules.

    The model is inconsistent about "every stage needs a growth step", so one
    corrective pass beats failing the whole request on the first slip.

    `university_requirements` is backend-computed (see `_university_requirements_for`)
    and never part of the LLM's JSON schema — it is only surfaced to the model as
    reference facts (via `build_messages`) and stapled onto the validated plan
    afterwards, same as `skills_to_build`/`university_track` are the model's call
    but this field never is. `gap` is the same kind of backend-only fact block,
    only ever populated for the generate-by-program university path."""
    messages = direction_prompt.build_messages(context, direction, university_requirements, gap=gap)

    for attempt in range(1, _MAX_PLAN_ATTEMPTS + 1):
        try:
            raw = await llm_client.complete_json(
                messages,
                direction_prompt.DIRECTION_ROADMAP_SCHEMA,
                "direction_roadmap",
                timeout=settings.LLM_ROADMAP_TIMEOUT,
                max_tokens=settings.LLM_ROADMAP_MAX_TOKENS,
                model=settings.LLM_ROADMAP_MODEL,
            )
            plan = _DirectionPlan(
                target=RoadmapTarget.model_validate(raw.get("target", {})),
                growth_focus=GrowthFocus.model_validate(raw.get("growth_focus", {})),
                stages=[DirectionStage.model_validate(s) for s in raw.get("stages", [])],
                skills_to_build=list(raw.get("skills_to_build", [])),
                subjects_to_focus=list(raw.get("subjects_to_focus", [])),
                university_track=UniversityTrack.model_validate(
                    raw.get("university_track", {})
                ),
                university_requirements=university_requirements,
            )
        except (llm_client.LLMError, ValidationError, TypeError) as exc:
            logger.warning("Direction roadmap generation failed: %s", exc)
            return None

        if _valid_plan(plan):
            return plan

        logger.warning(
            "Direction roadmap failed invariant check (attempt %s/%s)",
            attempt, _MAX_PLAN_ATTEMPTS,
        )
        messages = [*messages, direction_prompt.RETRY_HINT]

    return None


async def generate_direction_roadmap(
    assessment_id: uuid.UUID, slug: str, db: AsyncSession
) -> DirectionRoadmapResponse:
    """Build the in-direction development plan. Confirming a direction happens here:
    generating its roadmap is what marks it as the student's chosen path."""
    if not llm_client.is_enabled():
        raise _AI_UNAVAILABLE

    redis = _get_redis()
    key = direction_cache_key(assessment_id, slug)
    cached = await redis.get(key)
    if cached:
        return DirectionRoadmapResponse.model_validate_json(cached)

    assessment, direction = await _require_direction_roadmap_access(assessment_id, slug, db)

    context = await build_student_context(assessment_id, db, inquiry_slug=slug)
    if context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    # Backend-only university facts — never the model's job, and never asked of
    # it for any goal other than "university". Gated on the EFFECTIVE goal
    # (context.goal, already resolved by build_student_context) — a middle
    # assessment stored as raw "university" runs as "profession" end to end,
    # so it must not get university facts sprinkled into its prompt either.
    university_requirements: list[UniversityRequirement] = []
    if AssessmentGoal(context.goal) == AssessmentGoal.university:
        university_requirements = await _university_requirements_for(slug, db)

    plan = await _generate_plan(context, direction, university_requirements)
    if plan is None:
        raise _AI_UNAVAILABLE

    roadmap = await _upsert_direction_roadmap(assessment_id, slug, direction, plan, db)
    assessment.selected_direction_slug = slug
    from app.services.goal_overlay_service import invalidate_goal_overlay_cache
    await invalidate_goal_overlay_cache(assessment_id, db)
    await db.commit()
    await db.refresh(roadmap)

    response = DirectionRoadmapResponse.model_validate(roadmap)
    await redis.setex(key, CACHE_TTL, response.model_dump_json())
    return response


async def generate_direction_roadmap_for_program(
    assessment_id: uuid.UUID, program_id: uuid.UUID, db: AsyncSession
) -> DirectionRoadmapResponse:
    """University scenario (C) entry point: same direction-roadmap engine as
    `generate_direction_roadmap`, but driven by a chosen Program instead of a
    direction slug, and without the AI-inquiry precondition (see
    `_require_direction_roadmap_access` — picking a program and seeing its
    gap-analysis already is this scenario's "does it fit" check).

    The direction is resolved server-side from `program.profession_slugs`
    against the student's own `careers` (`direction_service.best_matching_slug`)
    — never trust a client-supplied slug for this. The plan is grounded in the
    real gap-analysis for this exact program (`analyze_gap`) plus this one
    program's facts, not every program that happens to prepare for the same
    direction (contrast `_university_requirements_for`)."""
    if not llm_client.is_enabled():
        raise _AI_UNAVAILABLE

    assessment = (
        await db.execute(select(Assessment).where(Assessment.id == assessment_id))
    ).scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    profile = (
        await db.execute(select(Profile).where(Profile.id == assessment.profile_id))
    ).scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    if profile.age_group == AgeGroup.junior:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Эта возможность доступна с 10 лет",
        )

    program_university = await _program_and_university(program_id, db)
    if program_university is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Program not found")
    program, university = program_university

    analysis_row = await db.execute(
        select(AnalysisResult).where(AnalysisResult.assessment_id == assessment_id)
    )
    analysis = analysis_row.scalar_one_or_none()
    careers: list = analysis.careers if analysis else []
    slug = direction_service.best_matching_slug(program.profession_slugs or [], careers)
    if slug is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Эта программа не связана ни с одним направлением",
        )

    direction = await direction_service.get_direction_by_slug(slug, db)
    if direction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Direction not found")

    redis = _get_redis()
    key = direction_cache_key(assessment_id, slug, program_id)
    cached = await redis.get(key)
    if cached:
        return DirectionRoadmapResponse.model_validate_json(cached)

    context = await build_student_context(assessment_id, db)
    if context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    artifacts_row = await db.execute(
        select(Artifact).where(Artifact.profile_id == assessment.profile_id)
    )
    artifacts = list(artifacts_row.scalars().all())
    scores = await assessment_service.get_total_scores(assessment_id, db)
    gap = analyze_gap(profile, artifacts, scores, program)
    university_requirements = [ureq.map_program_requirement(program, university)]

    plan = await _generate_plan(context, direction, university_requirements, gap=gap)
    if plan is None:
        raise _AI_UNAVAILABLE

    roadmap = await _upsert_direction_roadmap(
        assessment_id, slug, direction, plan, db, program_id=program_id
    )
    assessment.selected_direction_slug = slug
    from app.services.goal_overlay_service import invalidate_goal_overlay_cache
    await invalidate_goal_overlay_cache(assessment_id, db)
    await db.commit()
    await db.refresh(roadmap)

    response = DirectionRoadmapResponse.model_validate(roadmap)
    await redis.setex(key, CACHE_TTL, response.model_dump_json())
    return response


async def _upsert_direction_roadmap(
    assessment_id: uuid.UUID,
    slug: str,
    direction: Direction,
    plan: "_DirectionPlan",
    db: AsyncSession,
    *,
    program_id: uuid.UUID | None = None,
) -> DirectionRoadmap:
    direction_name = direction.name
    existing = (
        await db.execute(
            select(DirectionRoadmap).where(
                DirectionRoadmap.assessment_id == assessment_id,
                DirectionRoadmap.direction_slug == slug,
            )
        )
    ).scalar_one_or_none()

    if existing is None:
        roadmap = DirectionRoadmap(
            assessment_id=assessment_id,
            direction_slug=slug,
            direction_name=direction_name,
        )
        db.add(roadmap)
    else:
        roadmap = existing

    # Deterministic, non-LLM catalogue match off the direction's own fields —
    # see app/data/resource_catalog.py.
    category = resource_catalog.match_category(
        direction.name,
        " ".join(direction.skills_needed or []),
        " ".join(direction.subjects_to_develop or []),
        direction.holland_code,
    )

    roadmap.direction_name = direction_name
    roadmap.target = plan.target.model_dump()
    roadmap.growth_focus = plan.growth_focus.model_dump()
    roadmap.stages = [s.model_dump() for s in plan.stages]
    roadmap.skills_to_build = plan.skills_to_build
    roadmap.subjects_to_focus = plan.subjects_to_focus
    roadmap.university_track = plan.university_track.model_dump()
    roadmap.university_requirements = [r.model_dump() for r in plan.university_requirements]
    roadmap.additional_resources = resource_catalog.resources_for_category(category)
    # Always set explicitly (including back to None) — a row previously
    # generated by-program and later regenerated via the plain slug path
    # must not keep pointing at a program whose facts are no longer what
    # `university_requirements` above actually reflects.
    roadmap.program_id = program_id
    return roadmap


async def get_direction_roadmap(
    assessment_id: uuid.UUID, slug: str, db: AsyncSession
) -> DirectionRoadmapResponse | None:
    redis = _get_redis()
    key = direction_cache_key(assessment_id, slug)

    cached = await redis.get(key)
    if cached:
        return DirectionRoadmapResponse.model_validate_json(cached)

    roadmap = (
        await db.execute(
            select(DirectionRoadmap).where(
                DirectionRoadmap.assessment_id == assessment_id,
                DirectionRoadmap.direction_slug == slug,
            )
        )
    ).scalar_one_or_none()
    if roadmap is None:
        return None

    response = DirectionRoadmapResponse.model_validate(roadmap)
    await redis.setex(key, CACHE_TTL, response.model_dump_json())
    return response
