"""GET /api/v1/psychologist/students/{student_id}/assessments/{assessment_id}/report
(PRO-338 Ф0.3) — the specialist-only surface for the main report + the 6
new-tests sections. Never exposed to the student's own /result."""
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_result import AnalysisResult
from app.models.assessment import Assessment, AssessmentGoal
from app.models.assessment_validity import AssessmentValidity, SdLevel, TrafficLight
from app.models.astur_run import AsturRun
from app.models.belbin_run import BelbinRun
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from scripts.astur_bank import AWARENESS_ITEMS


async def _make_assessment_for(db: AsyncSession, owner: User) -> Assessment:
    profile = Profile(
        user_id=owner.id, name="Тест", age=16, grade=10, city="Алматы",
        country="Казахстан", language="ru", age_group=AgeGroup.senior,
    )
    db.add(profile)
    await db.flush()
    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db.add(assessment)
    await db.flush()
    return assessment


def _minimal_report_kwargs(assessment_id: uuid.UUID) -> dict:
    """riasec-shaped (not empty `profile`, so `_shape_response` picks the
    riasec branch, not the mi/junior one — see
    report_service._stored_interest_instrument)."""
    return dict(
        assessment_id=assessment_id,
        summary="Итоговое summary",
        profile={"R": 50.0, "I": 40.0, "A": 30.0, "S": 20.0, "E": 10.0, "C": 5.0},
        code=["R", "I", "A"],
        meta={"differentiation": 40.0, "consistency": "high", "aversion": {}},
        careers=[],
        strengths=["R"],
        weaknesses=["C"],
        development_plan={"reinforce": [], "compensate": []},
        big_five={},
        thinking_style={"creative_think": 0.0, "systematic": 0.0, "strategic": 0.0, "practical": 0.0},
        personality_highlights=[],
        motivation={},
        motivation_top=[],
        motivation_highlights=[],
        personality_profile={
            "openness": 50.0, "conscientiousness": 50.0, "extraversion": 50.0,
            "agreeableness": 50.0, "emotional_stability": 50.0,
        },
        personality_notes={},
        report_version=2,
        strength_cards=[{"title": "Сильная сторона", "description": "..."}],
        thinking_style_notes=[{"title": "Стиль мышления", "description": "..."}],
    )


async def _assign(client: httpx.AsyncClient, admin_headers: dict, psychologist_id: uuid.UUID, student_id: uuid.UUID) -> None:
    response = await client.post(
        "/api/v1/admin/psychologist-assignments",
        json={"psychologist_id": str(psychologist_id), "student_id": str(student_id)},
        headers=admin_headers,
    )
    assert response.status_code == 201


async def test_non_psychologist_non_admin_gets_403(
    client: httpx.AsyncClient, auth_headers: dict[str, str], test_user: User
) -> None:
    response = await client.get(
        f"/api/v1/psychologist/students/{test_user.id}/assessments/{uuid.uuid4()}/report",
        headers=auth_headers,
    )
    assert response.status_code == 403


async def test_unassigned_student_returns_404(
    client: httpx.AsyncClient,
    psychologist_headers: dict[str, str],
    test_user: User,
) -> None:
    """Psychologist role accepted, but no assignment row for this student —
    same "missing → 404, not 403" idiom as get_student."""
    response = await client.get(
        f"/api/v1/psychologist/students/{test_user.id}/assessments/{uuid.uuid4()}/report",
        headers=psychologist_headers,
    )
    assert response.status_code == 404


async def test_admin_without_assignment_returns_404_not_403(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    admin_user: User,
    test_user: User,
) -> None:
    """Confirms require_role admits admin (a bare role mismatch would be
    403) — the endpoint still needs the same assignment row admin or not."""
    response = await client.get(
        f"/api/v1/psychologist/students/{test_user.id}/assessments/{uuid.uuid4()}/report",
        headers=admin_headers,
    )
    assert response.status_code == 404


async def test_assessment_belonging_to_a_different_student_returns_404(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    """Assigned to `test_user`, but the assessment_id in the URL belongs to
    someone else entirely — must not leak that other student's report."""
    await _assign(client, admin_headers, psychologist_user.id, test_user.id)
    other_user = User(email=f"{uuid.uuid4()}@example.test", hashed_password="x")
    db_session.add(other_user)
    await db_session.flush()
    other_assessment = await _make_assessment_for(db_session, other_user)

    response = await client.get(
        f"/api/v1/psychologist/students/{test_user.id}/assessments/{other_assessment.id}/report",
        headers=psychologist_headers,
    )
    assert response.status_code == 404


async def test_no_report_yet_returns_404(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    await _assign(client, admin_headers, psychologist_user.id, test_user.id)
    assessment = await _make_assessment_for(db_session, test_user)

    response = await client.get(
        f"/api/v1/psychologist/students/{test_user.id}/assessments/{assessment.id}/report",
        headers=psychologist_headers,
    )
    assert response.status_code == 404


async def test_full_report_with_new_tests_section_isolation(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    """200 with the main report plus the 6 new-tests sections — one
    malformed container (`eysenck`, an unknown field under extra='forbid')
    must not blank the others or fail the whole request."""
    await _assign(client, admin_headers, psychologist_user.id, test_user.id)
    assessment = await _make_assessment_for(db_session, test_user)
    analysis = AnalysisResult(
        **_minimal_report_kwargs(assessment.id),
        professional_types={"interest_scores": {"practical": 5}},
        eysenck={"not_a_real_field": 1},
        elers={"score": 20, "level": "high"},
    )
    db_session.add(analysis)
    await db_session.flush()

    response = await client.get(
        f"/api/v1/psychologist/students/{test_user.id}/assessments/{assessment.id}/report",
        headers=psychologist_headers,
    )
    assert response.status_code == 200
    body = response.json()

    assert body["report"]["assessment_id"] == str(assessment.id)
    assert body["report"]["interest_instrument"] == "riasec"

    new_tests = body["new_tests"]
    assert new_tests["professional_types"]["interest_scores"] == {"practical": 5}
    assert new_tests["aspiration_level"]["score"] == 20
    assert new_tests["temperament"] is None
    assert new_tests["team_role"] is None
    assert new_tests["intelligence"] is None
    assert new_tests["empathy_confidence"] is None


async def test_team_role_section_reads_the_latest_belbin_run(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    """Ф2.7 — unlike every other new-tests section, team_role's source is
    the separate `belbin_runs` table, not an AnalysisResult JSONB column.
    Two runs are seeded to confirm the report reads the LATEST one, not the
    first (append-only history, Ф2.3)."""
    await _assign(client, admin_headers, psychologist_user.id, test_user.id)
    assessment = await _make_assessment_for(db_session, test_user)
    analysis = AnalysisResult(**_minimal_report_kwargs(assessment.id))
    db_session.add(analysis)

    stale_totals = {
        "implementer": 5, "coordinator": 5, "shaper": 5, "plant": 5,
        "resource_investigator": 5, "evaluator": 5, "team_worker": 15, "finisher": 25,
    }
    latest_totals = {
        "implementer": 3, "coordinator": 20, "shaper": 14, "plant": 2,
        "resource_investigator": 8, "evaluator": 8, "team_worker": 8, "finisher": 7,
    }
    # Explicit created_at: the whole test runs inside one wrapped
    # transaction (tests/conftest.py's savepoint fixture), so Postgres'
    # now() is frozen for the transaction's duration — two server-defaulted
    # timestamps here would tie, unlike real separate requests.
    now = datetime.now(timezone.utc)
    db_session.add(BelbinRun(
        assessment_id=assessment.id, user_id=test_user.id,
        allocations=[], role_totals=stale_totals,
        created_at=now - timedelta(minutes=5),
    ))
    await db_session.flush()
    db_session.add(BelbinRun(
        assessment_id=assessment.id, user_id=test_user.id,
        allocations=[], role_totals=latest_totals,
        created_at=now,
    ))
    await db_session.flush()

    response = await client.get(
        f"/api/v1/psychologist/students/{test_user.id}/assessments/{assessment.id}/report",
        headers=psychologist_headers,
    )
    assert response.status_code == 200
    team_role = response.json()["new_tests"]["team_role"]

    assert team_role["scores"] == latest_totals
    assert team_role["dominant_role"] == "coordinator"
    assert team_role["supporting_roles"] == ["shaper", "resource_investigator"]
    assert set(team_role["avoidance_roles"]) == {"implementer", "plant"}
    assert team_role["ranked_roles"][0] == "coordinator"
    assert team_role["methodological_note"]


async def test_intelligence_section_reads_the_latest_astur_run(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    """Ф3.7 — same "separate append-only table, not an AnalysisResult JSONB
    column" shape as team_role (Ф2.7). Two runs seeded to confirm the
    report reads the LATEST one. Only 1 of 20 «Осведомлённость» items
    answered (correctly) — scoring degrades gracefully on a partial
    attempt (astur_scoring.py's own contract), no need to fill all 98."""
    await _assign(client, admin_headers, psychologist_user.id, test_user.id)
    assessment = await _make_assessment_for(db_session, test_user)
    analysis = AnalysisResult(**_minimal_report_kwargs(assessment.id))
    db_session.add(analysis)

    now = datetime.now(timezone.utc)
    db_session.add(AsturRun(
        assessment_id=assessment.id, user_id=test_user.id,
        answers={"awareness": {"1": "wrong answer"}},
        created_at=now - timedelta(minutes=10),
    ))
    await db_session.flush()
    db_session.add(AsturRun(
        assessment_id=assessment.id, user_id=test_user.id,
        answers={"awareness": {"1": AWARENESS_ITEMS[0]["answer"]["ru"]}},
        lability_answers={
            str(i): {"answer": "x", "elapsed_ms": 1000, "over_limit": False} for i in range(1, 9)
        },
        created_at=now,
    ))
    await db_session.flush()

    response = await client.get(
        f"/api/v1/psychologist/students/{test_user.id}/assessments/{assessment.id}/report",
        headers=psychologist_headers,
    )
    assert response.status_code == 200
    intelligence = response.json()["new_tests"]["intelligence"]

    assert intelligence["subtest_scores"]["awareness"] == 1
    assert intelligence["raw_score"] == 1
    assert intelligence["spn_group"] is not None
    assert intelligence["lability_first_half_accuracy"] is not None
    assert intelligence["lability_second_half_accuracy"] is not None


async def test_pro282_validity_section_is_attached_for_the_psychologist_viewer(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_headers: dict[str, str],
    psychologist_headers: dict[str, str],
    psychologist_user: User,
    test_user: User,
) -> None:
    """Ф4.1 — before this fix, `get_assigned_student_report` built its
    response via `get_report_with_analysis()` WITHOUT ever calling
    `_attach_psych_sections`, so PRO-282's `validity`/`psychoemotional`
    stayed `null` here even though PRO-282 is already merged into this
    backend branch and a psychologist viewer should see them (same
    `psych_sections_for` gate `/result` itself uses)."""
    await _assign(client, admin_headers, psychologist_user.id, test_user.id)
    assessment = await _make_assessment_for(db_session, test_user)
    analysis = AnalysisResult(**_minimal_report_kwargs(assessment.id))
    db_session.add(analysis)
    db_session.add(AssessmentValidity(
        assessment_id=assessment.id,
        sd_raw=4, sd_level=SdLevel.ok,
        longstring_max=3, irv=1.2, infrequency_failed=0, careless_flag=False,
        traffic_light=TrafficLight.green,
        thresholds_version=1,
    ))
    await db_session.flush()

    response = await client.get(
        f"/api/v1/psychologist/students/{test_user.id}/assessments/{assessment.id}/report",
        headers=psychologist_headers,
    )
    assert response.status_code == 200
    validity = response.json()["report"]["validity"]

    assert validity is not None
    assert validity["sd_raw"] == 4
    assert validity["traffic_light"] == "green"
