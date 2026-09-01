"""Development plan service — DB-backed, LLM mocked. Needs db+redis (Docker)."""
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.analysis_result import AnalysisResult
from app.models.assessment import Assessment, AssessmentGoal
from app.models.direction import Direction
from app.models.profile import AgeGroup, Profile
from app.models.program import Program, program_directions
from app.models.university import University
from app.models.user import User
from app.services import development_plan_service as svc
from app.services import llm_client

SLUG = "devplan-test-direction"


async def _seed(db: AsyncSession, *, age_group=AgeGroup.senior, country="Казахстан"):
    user = User(email=f"{uuid.uuid4()}@t.local", hashed_password="x")
    db.add(user)
    await db.flush()
    profile = Profile(
        user_id=user.id, name="S", age=17, grade=11, city="Астана",
        country="Казахстан", language="ru", age_group=age_group,
        subjects_hard=["математика"],
    )
    db.add(profile)
    await db.flush()
    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.profession)
    db.add(assessment)
    await db.flush()
    db.add(AnalysisResult(
        assessment_id=assessment.id, summary="s", profile={"E": 70.0, "I": 40.0},
        code=["E", "I", "C"], strengths=["E"], weaknesses=["I"],
        careers=[{"slug": SLUG, "name": "Тест-профессия", "match_score": 88}],
        personality_notes={"extraversion": "тебе комфортнее в спокойной обстановке"},
        thinking_style={"systematic": 60.0}, motivation_top=["interest"],
    ))
    direction = Direction(name="Тест-направление", slug=SLUG, holland_code="ECI",
                          skills_needed=["навык"], first_steps=["шаг"])
    db.add(direction)
    university = University(name="Тест-универ", country=country, city="Астана",
                            website="https://u.example")
    db.add(university)
    await db.flush()
    program = Program(
        university_id=university.id, name="Тест-специальность", language="русский",
        requirements={"exams": ["Математика", "Информатика"]},
        deadlines={"application_close": "2026-07-20"}, grants=[],
    )
    db.add(program)
    await db.flush()
    await db.execute(program_directions.insert().values(
        program_id=program.id, direction_id=direction.id
    ))
    await db.flush()
    return user, profile, assessment, program


def _skeleton(is_foreign=False):
    slots = ["autumn_11", "winter_11", "spring_11", "summer_11"]
    def tasks(slot):
        base = [
            {"track": "ent", "title": f"{slot}-ent", "why": "w", "done_when": "d"},
            {"track": "profession", "title": f"{slot}-prof", "why": "w", "done_when": "d"},
            {"track": "growth", "title": f"{slot}-growth", "why": "w", "done_when": "d"},
        ]
        if is_foreign and slot == "autumn_11":
            base.append({"track": "language", "title": f"{slot}-lang", "why": "w", "done_when": "d"})
        return base
    return {
        "target": {"role": "Аналитик", "why": "y", "university_name": "u", "specialty": "s"},
        "about_you": {"strengths": ["логика"], "growth": {"area": "x", "why": "y", "evidence": "низкая I"}},
        "skills": ["анализ"],
        "stages": [{"slot": s, "label": s, "outcome": "готово", "tasks": tasks(s)} for s in slots],
    }


def _stage_expansion(payload_tasks):
    return {
        "tasks": [
            {
                "title": t["title"],
                "steps": [{
                    "title": "шаг",
                    "actions": [
                        {"text": "Разбери тему по видео и реши задачи", "time": "нед", "kind": "repeat", "count_target": 4},
                        {"text": "Сверь ответы", "time": "20 мин", "kind": "once", "count_target": None},
                    ],
                }],
            }
            for t in payload_tasks
        ]
    }


@pytest.fixture
def _mock_llm(monkeypatch):
    monkeypatch.setattr(llm_client, "is_enabled", lambda: True)
    state = {"foreign": False}

    async def fake_complete_json(messages, schema, schema_name, **kw):
        if schema_name == "devplan_skeleton":
            return _skeleton(state["foreign"])
        # devplan_stage: echo the tasks passed in the user message
        import json, re
        user = messages[1]["content"] if len(messages) > 1 else messages[0]["content"]
        m = re.search(r"ЗАДАЧИ ЭТАПА:\n(\[.*?\])\n\n", user, re.S)
        tasks = json.loads(m.group(1)) if m else [{"title": "x"}]
        return _stage_expansion(tasks)

    monkeypatch.setattr(llm_client, "complete_json", fake_complete_json)
    monkeypatch.setattr(settings, "DEVELOPMENT_PLAN_ENABLED", True)
    return state


async def test_happy_path_local(db_session, _mock_llm):
    user, _, assessment, program = await _seed(db_session)
    await db_session.flush()
    out = await svc.generate_development_plan(assessment.id, program.id, user.id, db_session)
    assert len(out.stages) == 4
    assert out.is_foreign is False
    assert out.direction_slug == SLUG
    # every stage has at least one repeat action
    for stage in out.stages:
        actions = [a for t in stage.tasks for s in t.steps for a in s.actions]
        assert any(a.kind == "repeat" for a in actions)
    # facts come straight from the program
    assert "Математика" in out.admission_facts.exams
    # about_you.growth may be null (no invented weakness)
    assert out.about_you.strengths


async def test_happy_path_foreign(db_session, _mock_llm):
    _mock_llm["foreign"] = True
    user, _, assessment, program = await _seed(db_session, country="Великобритания")
    await db_session.flush()
    out = await svc.generate_development_plan(assessment.id, program.id, user.id, db_session)
    assert out.is_foreign is True
    assert out.admission_facts.foreign_route
    assert out.admission_facts.language_exam
    tracks = {t.track for st in out.stages for t in st.tasks}
    assert "language" in tracks


async def test_llm_off_returns_503(db_session, _mock_llm, monkeypatch):
    monkeypatch.setattr(llm_client, "is_enabled", lambda: False)
    user, _, assessment, program = await _seed(db_session)
    await db_session.flush()
    with pytest.raises(HTTPException) as exc:
        await svc.generate_development_plan(assessment.id, program.id, user.id, db_session)
    assert exc.value.status_code == 503


async def test_feature_flag_off_returns_404(db_session, _mock_llm, monkeypatch):
    monkeypatch.setattr(settings, "DEVELOPMENT_PLAN_ENABLED", False)
    user, _, assessment, program = await _seed(db_session)
    await db_session.flush()
    with pytest.raises(HTTPException) as exc:
        await svc.generate_development_plan(assessment.id, program.id, user.id, db_session)
    assert exc.value.status_code == 404


async def test_non_senior_returns_403(db_session, _mock_llm):
    user, _, assessment, program = await _seed(db_session, age_group=AgeGroup.middle)
    await db_session.flush()
    with pytest.raises(HTTPException) as exc:
        await svc.generate_development_plan(assessment.id, program.id, user.id, db_session)
    assert exc.value.status_code == 403


async def test_second_call_is_served_from_cache(db_session, _mock_llm):
    user, _, assessment, program = await _seed(db_session)
    await db_session.flush()
    first = await svc.generate_development_plan(assessment.id, program.id, user.id, db_session)
    second = await svc.get_development_plan(assessment.id, program.id, user.id, db_session)
    assert second is not None
    assert second.id == first.id
