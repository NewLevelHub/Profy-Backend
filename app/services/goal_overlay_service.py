import json
import logging
import uuid
from typing import Literal, Optional

import redis.asyncio as aioredis
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.analysis_result import AnalysisResult
from app.i18n import DEFAULT_LOCALE
from app.models.assessment import Assessment, AssessmentGoal
from app.models.direction import Direction
from app.models.goal_overlay import GoalOverlay
from app.models.profile import AgeGroup, Profile
from app.models.program import Program
from app.schemas.goal_overlay import (
    BridgeScenario,
    GoalOverlayResponse,
    ScenarioAData,
    ScenarioBData,
    ScenarioCData,
)
from app.services import assessment_shared
from app.services.gap_analysis_service import analyze_gap
from app.services.gap_analysis_service import to_response as gap_to_response
from app.services.mi_content import MI_LABELS
from app.services.riasec_content import RIASEC_LABELS
from app.services.roadmap_builder import generate_roadmap

logger = logging.getLogger(__name__)

CACHE_TTL = 60 * 60 * 24  # 24 hours
_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def get_cache_key(assessment_id: uuid.UUID, goal: AssessmentGoal) -> str:
    return f"goal_context:{assessment_id}:{goal.value}"


async def get_cached_overlay(assessment_id: uuid.UUID, goal: AssessmentGoal) -> Optional[GoalOverlayResponse]:
    redis = _get_redis()
    key = get_cache_key(assessment_id, goal)
    try:
        cached = await redis.get(key)
        if cached:
            return GoalOverlayResponse.model_validate_json(cached)
    except Exception as exc:
        logger.warning("Failed to get cached goal overlay for %s: %s", key, exc)
    return None


async def set_cached_overlay(assessment_id: uuid.UUID, goal: AssessmentGoal, overlay: GoalOverlayResponse) -> None:
    redis = _get_redis()
    key = get_cache_key(assessment_id, goal)
    try:
        await redis.setex(key, CACHE_TTL, overlay.model_dump_json())
    except Exception as exc:
        logger.warning("Failed to cache goal overlay for %s: %s", key, exc)


async def invalidate_goal_overlay_cache(assessment_id: uuid.UUID, db: AsyncSession) -> None:
    redis = _get_redis()
    try:
        # Delete from DB
        await db.execute(GoalOverlay.__table__.delete().where(GoalOverlay.assessment_id == assessment_id))
        # Scan and delete keys matching the assessment
        pattern = f"goal_context:{assessment_id}:*"
        keys = []
        async for key in redis.scan_iter(match=pattern):
            keys.append(key)
        if keys:
            await redis.delete(*keys)
            logger.info("Invalidated goal overlay caches: %s", keys)
    except Exception as exc:
        logger.warning("Failed to invalidate goal overlay caches for %s: %s", assessment_id, exc)


_SCENARIO_BY_GOAL: dict[AssessmentGoal, Literal["A", "B", "C"]] = {
    AssessmentGoal.explore: "A",
    AssessmentGoal.profession: "B",
    AssessmentGoal.university: "C",
}

_MIDDLE_UNIVERSITY_DOWNGRADE_NOTE = (
    "Для учеников 5-8 классов поступление в вуз еще впереди. "
    "Сейчас самое время определиться с интересными профессиями и направлениями, "
    "поэтому мы подготовили для тебя отчёт по выбору профессии."
)


def _get_effective_goal_and_scenario(
    age_group: AgeGroup, primary_goal: AssessmentGoal
) -> tuple[AssessmentGoal, Literal["A", "B", "C"], bool, Optional[str]]:
    """Display-layer wrapper around `assessment_shared.get_effective_goal` — the
    scenario letter and "redirected" banner text shown here must always agree
    with what roadmap/report generation actually runs under, so the goal
    mapping itself lives in that one shared function, not here."""
    effective_goal = assessment_shared.get_effective_goal(age_group, primary_goal)
    scenario = _SCENARIO_BY_GOAL[effective_goal]

    if age_group == AgeGroup.junior:
        redirected = primary_goal != AssessmentGoal.explore
        return effective_goal, scenario, redirected, None

    if age_group == AgeGroup.middle and primary_goal == AssessmentGoal.university:
        return effective_goal, scenario, True, _MIDDLE_UNIVERSITY_DOWNGRADE_NOTE

    return effective_goal, scenario, False, None


def _get_secondary_goals(age_group: AgeGroup, effective_goal: AssessmentGoal) -> list[AssessmentGoal]:
    if age_group == AgeGroup.junior:
        return []
    if age_group == AgeGroup.middle:
        return [AssessmentGoal.profession] if effective_goal == AssessmentGoal.explore else [AssessmentGoal.explore]
    
    # senior
    all_goals = [AssessmentGoal.explore, AssessmentGoal.profession, AssessmentGoal.university]
    return [g for g in all_goals if g != effective_goal]


async def _stored_interest_instrument(analysis: AnalysisResult) -> str:
    # mi keys are lowercase words, riasec keys are single uppercase letters
    return "riasec" if any(key in "RIASEC" for key in getattr(analysis, "profile", {})) else "mi"


def _build_alignment_evidence(
    user_code: list[str],
    direction_code: str,
) -> BridgeScenario:
    holland_descriptions = {
        "R": "практические навыки и интерес к технике/материальным объектам",
        "I": "аналитическое мышление, склонность к исследованиям и решению сложных задач",
        "A": "творческое воображение, нестандартный подход и самовыражение",
        "S": "стремление помогать людям, развитые навыки коммуникации и работы в команде",
        "E": "лидерские качества, инициативность и организаторские способности",
        "C": "внимание к деталям, умение работать со структурированной информацией",
    }
    
    holland_actions = {
        "R": "Пройти практическую профессиональную пробу (например, собрать прототип устройства или выполнить чертеж).",
        "I": "Решить прикладную аналитическую задачу в этой сфере или изучить научное исследование по теме.",
        "A": "Создать творческий концепт, эскиз или сценарий, связанный с этой специальностью.",
        "S": "Поучаствовать в волонтерском проекте или провести интервью с практикующим специалистом.",
        "E": "Разработать мини-план продвижения или попробовать организовать командное мероприятие.",
        "C": "Составить детальный чек-лист требований или систематизировать данные по проекту.",
    }
    
    direction_letters = set(direction_code or "")
    user_letters = set(user_code)
    overlapping_letters = direction_letters.intersection(user_letters)
    
    what_works = []
    for letter in (direction_code or ""):
        if letter in overlapping_letters:
            what_works.append(f"Твой выраженный интерес к сфере: {holland_descriptions.get(letter)}")
            
    if not what_works and direction_code:
        first_letter = direction_code[0]
        what_works.append(f"Твои общие склонности, хотя сфера требует: {holland_descriptions.get(first_letter)}")
        
    what_to_check = []
    for letter in (direction_code or ""):
        action = holland_actions.get(letter)
        if action and action not in what_to_check:
            what_to_check.append(action)
            
    return BridgeScenario(
        what_works=what_works,
        what_to_check=what_to_check[:2],
    )


async def get_or_create_goal_overlay(
    assessment_id: uuid.UUID,
    db: AsyncSession,
    program_id: Optional[uuid.UUID] = None,
) -> GoalOverlayResponse:
    # 1. Fetch Assessment
    stmt = select(Assessment).where(Assessment.id == assessment_id)
    res = await db.execute(stmt)
    assessment = res.scalar_one_or_none()
    if not assessment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    primary_goal = assessment.goal

    # 2. Check cache first (skip cache if program_id is passed)
    if not program_id:
        cached = await get_cached_overlay(assessment_id, primary_goal)
        if cached:
            return cached

    # 3. Fetch Profile & Check completeness
    stmt = select(Profile).where(Profile.id == assessment.profile_id)
    res = await db.execute(stmt)
    profile = res.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    # 4. Handle unsure goal flow early
    if primary_goal == AssessmentGoal.unsure:
        if profile.age_group == AgeGroup.junior:
            suggested = [AssessmentGoal.explore]
        elif profile.age_group == AgeGroup.middle:
            suggested = [AssessmentGoal.explore, AssessmentGoal.profession]
        else:
            suggested = [AssessmentGoal.explore, AssessmentGoal.profession, AssessmentGoal.university]

        return GoalOverlayResponse(
            assessment_id=assessment_id,
            primary_goal=AssessmentGoal.unsure,
            effective_goal=None,
            scenario=None,
            secondary_goals=list(assessment.secondary_goals or []),
            redirected=False,
            admission_info_note=None,
            needs_goal_selection=True,
            suggested_goals=suggested,
            alignment_block=None,
            overlay_data=None,
        )

    # Re-check completeness (if not completed, raise conflict)
    from app.services.report_service import _assert_assessment_complete
    await _assert_assessment_complete(assessment_id, profile.age_group, db)

    # 5. Fetch AnalysisResult
    stmt = select(AnalysisResult).where(AnalysisResult.assessment_id == assessment_id)
    res = await db.execute(stmt)
    analysis = res.scalar_one_or_none()
    if not analysis:
        from app.services.report_service import build_report
        await build_report(assessment_id, db)
        res = await db.execute(stmt)
        analysis = res.scalar_one_or_none()
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Не удалось получить результаты диагностики",
            )

    # 6. Compute matrix rules
    effective_goal, scenario, redirected, admission_info_note = _get_effective_goal_and_scenario(
        profile.age_group, primary_goal
    )
    secondary_goals = list(assessment.secondary_goals or [])

    # Check if DB overlay exists for this primary goal
    stmt = select(GoalOverlay).where(
        GoalOverlay.assessment_id == assessment_id,
        GoalOverlay.goal == primary_goal,
    )
    res = await db.execute(stmt)
    db_overlay = res.scalar_one_or_none()

    # If overlay exists, and scenario is not C with a new program_id, we can deserialize and return it
    if db_overlay and not (scenario == "C" and program_id):
        try:
            response = GoalOverlayResponse.model_validate(db_overlay.data)
            await set_cached_overlay(assessment_id, primary_goal, response)
            return response
        except Exception as exc:
            logger.warning("Saved GoalOverlay model mismatch: %s. Re-generating.", exc)

    # 7. Generate Scenario Data and Alignment Block
    overlay_data = None
    alignment_block = None

    if scenario == "A":
        instrument = await _stored_interest_instrument(analysis)
        labels = MI_LABELS if instrument == "mi" else RIASEC_LABELS
        top_spheres = [labels[k] for k in analysis.strengths if k in labels]
        
        roadmap_summary = (
            f"Этот маршрут поможет тебе глубже изучить сферы {', '.join(top_spheres[:3])} "
            "через простые практические пробы и онлайн-исследования."
            if top_spheres
            else "Этот маршрут поможет тебе познакомиться с интересными сферами через пробы."
        )
        
        roadmap = await generate_roadmap(assessment_id, None, db)
        roadmap_id = roadmap.id

        overlay_data = ScenarioAData(
            top_spheres=top_spheres,
            roadmap_summary=roadmap_summary,
            roadmap_id=roadmap_id,
        )

    elif scenario == "B":
        careers = analysis.careers or []
        top_directions = [c.get("name") for c in careers[:3] if c.get("name")]
        overlay_data = ScenarioBData(top_directions=top_directions)

        target_selected = False
        selected_target_name = None
        alignment = "not_applicable"
        match_explanation = None
        bridge_scenario = None
        adjacent_names = []

        if assessment.selected_direction_slug:
            # Pin to `ru`: `directions.slug` is unique only per-locale since
            # KZ-301, so an unscoped slug lookup would raise MultipleResultsFound
            # once KZ-306 seeds `kk` rows. Overlay text stays `ru` here until a
            # later ticket localizes this service (the epic caches overlays by
            # locale) — `holland_code`, the only field driving scoring below, is
            # locale-invariant anyway.
            stmt = select(Direction).where(
                Direction.slug == assessment.selected_direction_slug,
                Direction.locale == DEFAULT_LOCALE,
            )
            res = await db.execute(stmt)
            direction = res.scalar_one_or_none()
            if direction:
                target_selected = True
                selected_target_name = direction.name
                
                career_index = next((i for i, c in enumerate(careers) if c.get("slug") == direction.slug), None)
                if career_index is not None:
                    if career_index <= 2:
                        alignment = "match"
                    elif career_index <= 9:
                        alignment = "partial"
                    else:
                        alignment = "bridge"
                    match_explanation = careers[career_index].get("why")
                else:
                    alignment = "bridge"
                    match_explanation = (
                        f"Направление «{direction.name}» не попало в твои основные рекомендации, "
                        "но это не значит, что оно тебе не подходит — его можно рассмотреть как смежное."
                    )

                user_code = analysis.strengths[:3] if analysis.strengths else []
                bridge_scenario = _build_alignment_evidence(user_code, direction.holland_code)

                if alignment == "bridge":
                    # `ru` set only — adjacency is scored on `holland_code`
                    # (locale-invariant); an unscoped select doubles the list
                    # once KZ-306 seeds `kk` directions.
                    stmt = select(Direction).where(Direction.locale == DEFAULT_LOCALE)
                    res = await db.execute(stmt)
                    all_directions = res.scalars().all()

                    adjacent = []
                    selected_set = set(direction.holland_code)
                    for d in all_directions:
                        if d.slug == direction.slug:
                            continue
                        overlap = len(selected_set.intersection(set(d.holland_code)))
                        if overlap >= 2:
                            adjacent.append(d)
                    
                    adjacent.sort(key=lambda d: (-len(selected_set.intersection(set(d.holland_code))), d.slug))
                    adjacent_names = [d.name for d in adjacent[:3]]

        from app.schemas.goal_overlay import GoalAlignmentBlock
        alignment_block = GoalAlignmentBlock(
            target_selected=target_selected,
            target_name=selected_target_name,
            alignment=alignment,
            match_explanation=match_explanation,
            bridge_scenario=bridge_scenario,
            adjacent_directions=adjacent_names,
        )

    else:
        # Scenario C: Admission (Senior only)
        if not program_id:
            from app.models.direction_roadmap import DirectionRoadmap
            roadmap_stmt = select(DirectionRoadmap.program_id).where(
                DirectionRoadmap.assessment_id == assessment_id,
                DirectionRoadmap.program_id.isnot(None),
            )
            roadmap_res = await db.execute(roadmap_stmt)
            program_id = roadmap_res.scalar()

        selected_program_id = None
        selected_program_name = None
        selected_university_name = None
        gap_analysis = None
        admission_roadmap_ref = None

        target_selected = False
        alignment = "not_applicable"
        match_explanation = None
        bridge_scenario = None
        adjacent_names = []

        if program_id:
            stmt = select(Program).where(Program.id == program_id)
            res = await db.execute(stmt)
            program = res.scalar_one_or_none()
            if program:
                target_selected = True
                selected_program_id = program.id
                selected_program_name = program.name
                
                university = program.university
                selected_university_name = university.name if university else None
                
                artifacts_stmt = select(Artifact).where(Artifact.profile_id == assessment.profile_id)
                res = await db.execute(artifacts_stmt)
                artifacts = list(res.scalars().all())
                
                from app.services import assessment_service
                scores = await assessment_service.get_total_scores(assessment_id, db)
                gap_result = analyze_gap(profile, artifacts, scores, program)
                gap_analysis = gap_to_response(program_id, gap_result)
                
                roadmap = await generate_roadmap(assessment_id, program_id, db)
                admission_roadmap_ref = roadmap.id

                careers = analysis.careers or []
                prof_slugs = program.profession_slugs or []
                
                best_index = None
                best_slug = None
                for slug in prof_slugs:
                    idx = next((i for i, c in enumerate(careers) if c.get("slug") == slug), None)
                    if idx is not None:
                        if best_index is None or idx < best_index:
                            best_index = idx
                            best_slug = slug
                
                if best_index is not None:
                    if best_index <= 2:
                        alignment = "match"
                    elif best_index <= 9:
                        alignment = "partial"
                    else:
                        alignment = "bridge"
                    match_explanation = careers[best_index].get("why")
                    matched_direction_slug = best_slug
                else:
                    alignment = "bridge"
                    match_explanation = "Данная программа готовит к профессиям за пределами твоих основных рекомендаций."
                    matched_direction_slug = prof_slugs[0] if prof_slugs else None

                if matched_direction_slug:
                    # Pin to `ru` — see the scenario-C selected-direction lookup
                    # above (slug unique per-locale since KZ-301).
                    stmt = select(Direction).where(
                        Direction.slug == matched_direction_slug,
                        Direction.locale == DEFAULT_LOCALE,
                    )
                    res = await db.execute(stmt)
                    direction = res.scalar_one_or_none()
                    if direction:
                        user_code = analysis.strengths[:3] if analysis.strengths else []
                        bridge_scenario = _build_alignment_evidence(user_code, direction.holland_code)

                        if alignment == "bridge":
                            # `ru` set only — adjacency scored on `holland_code`
                            # (locale-invariant); unscoped doubles after KZ-306.
                            stmt = select(Direction).where(Direction.locale == DEFAULT_LOCALE)
                            res = await db.execute(stmt)
                            all_directions = res.scalars().all()

                            adjacent = []
                            selected_set = set(direction.holland_code)
                            for d in all_directions:
                                if d.slug == direction.slug:
                                    continue
                                overlap = len(selected_set.intersection(set(d.holland_code)))
                                if overlap >= 2:
                                    adjacent.append(d)
                            adjacent.sort(key=lambda d: (-len(selected_set.intersection(set(d.holland_code))), d.slug))
                            adjacent_names = [d.name for d in adjacent[:3]]

        overlay_data = ScenarioCData(
            selected_program_id=selected_program_id,
            selected_program_name=selected_program_name,
            selected_university_name=selected_university_name,
            gap_analysis=gap_analysis,
            admission_roadmap_ref=admission_roadmap_ref,
        )

        from app.schemas.goal_overlay import GoalAlignmentBlock
        alignment_block = GoalAlignmentBlock(
            target_selected=target_selected,
            target_name=selected_program_name,
            alignment=alignment,
            match_explanation=match_explanation,
            bridge_scenario=bridge_scenario,
            adjacent_directions=adjacent_names,
        )

    # 8. Construct response
    response = GoalOverlayResponse(
        assessment_id=assessment_id,
        primary_goal=primary_goal,
        effective_goal=effective_goal,
        scenario=scenario,
        secondary_goals=secondary_goals,
        redirected=redirected,
        admission_info_note=admission_info_note,
        needs_goal_selection=False,
        suggested_goals=[],
        alignment_block=alignment_block,
        overlay_data=overlay_data,
    )

    # 9. Save or update DB row
    overlay_dict = response.model_dump()
    def _convert_uuids(obj):
        if isinstance(obj, dict):
            return {k: _convert_uuids(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_convert_uuids(i) for i in obj]
        elif isinstance(obj, uuid.UUID):
            return str(obj)
        return obj

    db_data = _convert_uuids(overlay_dict)

    if db_overlay:
        db_overlay.scenario = scenario
        db_overlay.data = db_data
    else:
        new_overlay = GoalOverlay(
            assessment_id=assessment_id,
            goal=primary_goal,
            scenario=scenario,
            data=db_data,
        )
        db.add(new_overlay)

    await db.commit()

    # 10. Set cache
    await set_cached_overlay(assessment_id, primary_goal, response)

    return response
