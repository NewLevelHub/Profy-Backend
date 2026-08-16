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


async def invalidate_goal_overlay_cache(assessment_id: uuid.UUID) -> None:
    redis = _get_redis()
    try:
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


def _get_effective_goal_and_scenario(
    age_group: AgeGroup, primary_goal: AssessmentGoal
) -> tuple[AssessmentGoal, Literal["A", "B", "C"], bool, Optional[str]]:
    # Junior: always explore (A)
    if age_group == AgeGroup.junior:
        if primary_goal != AssessmentGoal.explore:
            return AssessmentGoal.explore, "A", True, None
        return AssessmentGoal.explore, "A", False, None

    # Middle
    if age_group == AgeGroup.middle:
        if primary_goal == AssessmentGoal.university:
            return (
                AssessmentGoal.profession,
                "B",
                True,
                "Для учеников 5-8 классов поступление в вуз еще впереди. "
                "Сейчас самое время определиться с интересными профессиями и направлениями, "
                "поэтому мы подготовили для тебя отчёт по выбору профессии.",
            )
        elif primary_goal in (AssessmentGoal.explore, AssessmentGoal.unsure):
            return AssessmentGoal.explore, "A", False, None
        else:
            return AssessmentGoal.profession, "B", False, None

    # Senior
    if primary_goal in (AssessmentGoal.explore, AssessmentGoal.unsure):
        return AssessmentGoal.explore, "A", False, None
    elif primary_goal == AssessmentGoal.profession:
        return AssessmentGoal.profession, "B", False, None
    else:
        return AssessmentGoal.university, "C", False, None


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

    # 2. Check cache first (skip cache if program_id is passed, as it forces re-generation of C-data)
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

    # Re-check completeness (if not completed, raise conflict)
    # Avoid generating report logic if assessment is incomplete
    from app.services.report_service import _assert_assessment_complete
    await _assert_assessment_complete(assessment_id, profile.age_group, db)

    # 4. Fetch AnalysisResult
    stmt = select(AnalysisResult).where(AnalysisResult.assessment_id == assessment_id)
    res = await db.execute(stmt)
    analysis = res.scalar_one_or_none()
    if not analysis:
        # If complete but no AnalysisResult exists yet, we generate it first via report_service.build_report
        from app.services.report_service import build_report
        await build_report(assessment_id, db)
        res = await db.execute(stmt)
        analysis = res.scalar_one_or_none()
        if not analysis:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Не удалось получить результаты диагностики",
            )

    # 5. Compute matrix rules
    effective_goal, scenario, redirected, admission_info_note = _get_effective_goal_and_scenario(
        profile.age_group, primary_goal
    )
    secondary_goals = _get_secondary_goals(profile.age_group, effective_goal)

    # Check if DB overlay exists for this primary goal
    stmt = select(GoalOverlay).where(
        GoalOverlay.assessment_id == assessment_id,
        GoalOverlay.goal == primary_goal,
    )
    res = await db.execute(stmt)
    db_overlay = res.scalar_one_or_none()

    # If overlay exists, and scenario is not C with a new program_id, we can deserialize and return it
    if db_overlay and not (scenario == "C" and program_id):
        # deserialize saved data
        overlay_dict = db_overlay.data
        # Ensure overlay matches expected type shape
        try:
            response = GoalOverlayResponse.model_validate(overlay_dict)
            await set_cached_overlay(assessment_id, primary_goal, response)
            return response
        except Exception as exc:
            logger.warning("Saved GoalOverlay model mismatch: %s. Re-generating.", exc)

    # 6. Generate Scenario Data
    overlay_data = None

    if scenario == "A":
        instrument = await _stored_interest_instrument(analysis)
        labels = MI_LABELS if instrument == "mi" else RIASEC_LABELS
        top_spheres = [labels[k] for k in analysis.strengths if k in labels]
        
        # summary of roadmap
        roadmap_summary = (
            f"Этот маршрут поможет тебе глубже изучить сферы {', '.join(top_spheres[:3])} "
            "через простые практические пробы и онлайн-исследования."
            if top_spheres
            else "Этот маршрут поможет тебе познакомиться с интересными сферами через пробы."
        )
        
        # Fetch or generate exploratory roadmap
        roadmap = await generate_roadmap(assessment_id, None, db)
        roadmap_id = roadmap.id

        overlay_data = ScenarioAData(
            top_spheres=top_spheres,
            roadmap_summary=roadmap_summary,
            roadmap_id=roadmap_id,
        )

    elif scenario == "B":
        # Scenario B: Choose profession
        selected_target_name = None
        alignment = None
        match_explanation = None
        bridge_scenario = None
        adjacent_directions = []
        target_selected = False

        careers = analysis.careers or []
        top_directions = [c.get("name") for c in careers[:3] if c.get("name")]

        # Check if user selected a direction
        if assessment.selected_direction_slug:
            stmt = select(Direction).where(Direction.slug == assessment.selected_direction_slug)
            res = await db.execute(stmt)
            direction = res.scalar_one_or_none()
            if direction:
                target_selected = True
                selected_target_name = direction.name
                
                # Check match tier
                matched_career = next((c for c in careers if c.get("slug") == direction.slug), None)
                if matched_career:
                    alignment = matched_career.get("tier", "worth_trying")
                    match_explanation = matched_career.get("why")
                    
                    # Bridge scenario if match is weak/moderate or not in top 3
                    # (Let's check if alignment is not "strong")
                    if alignment != "strong":
                        what_works = matched_career.get("matched_strengths", [])
                        if not what_works:
                            what_works = ["Сфера частично пересекается с твоими интересами."]
                        
                        first_steps = matched_career.get("first_steps", [])
                        what_to_check = first_steps[:3] if first_steps else ["Попробуй базовые практические задания в этом направлении."]
                        
                        bridge_scenario = BridgeScenario(
                            what_works=what_works,
                            what_to_check=what_to_check,
                        )
                else:
                    # Selected direction is not in top matched list at all
                    alignment = "worth_trying"
                    match_explanation = (
                        f"Направление «{direction.name}» не попало в твои основные рекомендации, "
                        "но это не значит, что оно тебе не подходит — его можно рассмотреть как смежное."
                    )
                    bridge_scenario = BridgeScenario(
                        what_works=["Ты проявляешь интерес к этой профессии, что является хорошей стартовой точкой."],
                        what_to_check=list(direction.first_steps[:3]) if direction.first_steps else ["Изучи первый шаг в этой профессии."],
                    )

                # Adjacent directions (recommending other top careers excluding the selected one)
                adjacent_directions = [
                    c.get("name") for c in careers
                    if c.get("slug") != direction.slug and c.get("name")
                ][:3]

        overlay_data = ScenarioBData(
            target_selected=target_selected,
            selected_target_name=selected_target_name,
            alignment=alignment,
            match_explanation=match_explanation,
            bridge_scenario=bridge_scenario,
            adjacent_directions=adjacent_directions,
            top_directions=top_directions,
        )

    else:
        # Scenario C: Admission (Senior only)
        target_selected = False
        selected_program_id = None
        selected_program_name = None
        selected_university_name = None
        gap_analysis = None
        admission_roadmap_ref = None

        if program_id:
            stmt = select(Program).where(Program.id == program_id)
            res = await db.execute(stmt)
            program = res.scalar_one_or_none()
            if program:
                target_selected = True
                selected_program_id = program.id
                selected_program_name = program.name
                
                # Fetch university
                university = program.university
                selected_university_name = university.name if university else None
                
                # Compute Gap Analysis
                artifacts_stmt = select(Artifact).where(Artifact.profile_id == assessment.profile_id)
                res = await db.execute(artifacts_stmt)
                artifacts = list(res.scalars().all())
                
                from app.services import assessment_service
                scores = await assessment_service.get_total_scores(assessment_id, db)
                gap_result = analyze_gap(profile, artifacts, scores, program)
                
                # format response
                gap_analysis = gap_to_response(program_id, gap_result)
                
                # Generate admission roadmap
                roadmap = await generate_roadmap(assessment_id, program_id, db)
                admission_roadmap_ref = roadmap.id

        overlay_data = ScenarioCData(
            target_selected=target_selected,
            selected_program_id=selected_program_id,
            selected_program_name=selected_program_name,
            selected_university_name=selected_university_name,
            gap_analysis=gap_analysis,
            admission_roadmap_ref=admission_roadmap_ref,
        )

    # 7. Construct response
    response = GoalOverlayResponse(
        assessment_id=assessment_id,
        primary_goal=primary_goal,
        effective_goal=effective_goal,
        scenario=scenario,
        secondary_goals=secondary_goals,
        redirected=redirected,
        admission_info_note=admission_info_note,
        overlay_data=overlay_data,
    )

    # 8. Save or update DB row
    overlay_dict = response.model_dump()
    # We must convert UUID to string so JSONB serialization works seamlessly
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

    # 9. Set cache
    await set_cached_overlay(assessment_id, primary_goal, response)

    return response
