import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.akinator_question import AkinatorQuestion
from app.models.assessment import Assessment, AssessmentGoal
from app.models.assessment_session import AssessmentSession, SessionStatus
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.services import cluster_resolver_service
from scripts.seed_akinator_content import seed_professions, seed_sections


@pytest.mark.asyncio
async def test_resolve_cluster_never_declares_winner_below_threshold_after_budget(
    db_session: AsyncSession,
):
    """AC1: After 3 questions are answered, if the leader is still below the stop threshold,

    we must never declare a winner (remains a cluster).
    """
    # 1. Seed taxonomy so _leaf_profiles_for works
    section_ids, *_ = await seed_sections(db_session)
    await seed_professions(db_session, section_ids)

    # 2. Create user, profile, assessment
    user = User(email=f"{uuid.uuid4()}@test.local", hashed_password="x")
    db_session.add(user)
    await db_session.flush()

    profile = Profile(
        user_id=user.id,
        name="Test Student",
        age=16,
        grade=10,
        city="Test City",
        country="Test Country",
        language="ru",
        age_group=AgeGroup.senior,
    )
    db_session.add(profile)
    await db_session.flush()

    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db_session.add(assessment)
    await db_session.flush()

    # 3. Seed resolves_pair question
    q = AkinatorQuestion(
        kind="situational",
        depth=3,
        age_variant="senior",
        text="Test resolver question",
        options=[
            {"text": "Option 1", "axis_weights": {}},
            {"text": "Option 2", "axis_weights": {}},
        ],
        resolves_pair=["psychologist", "speech-therapist"],
        is_active=True,
        order=19,
    )
    db_session.add(q)
    await db_session.flush()

    # 4. Create session on the verge of budget exhaustion (resolve_step = 2)
    # Belief has two close leaders psychologist and speech-therapist, neither crosses the threshold t=0.6.
    belief = {
        "psychologist": 0.45,
        "speech-therapist": 0.45,
    }
    # fill other leaves with tiny probabilities to sum up to 1.0
    from app.models.direction import Direction
    leaves = (await db_session.execute(
        select(Direction.slug).where(Direction.is_leaf.is_(True))
    )).scalars().all()
    
    other_leaves = [l for l in leaves if l not in {"psychologist", "speech-therapist"}]
    tiny_p = 0.1 / len(other_leaves)
    for l in other_leaves:
        belief[l] = tiny_p

    # normalize belief sum to exactly 1.0
    total = sum(belief.values())
    belief = {k: v / total for k, v in belief.items()}

    session = AssessmentSession(
        assessment_id=assessment.id,
        belief=belief,
        asked_question_ids=[],
        asked_axis_families=[],
        step=10,
        resolve_step=2,  # next answer will make it 3 (budget exhausted)
        status=SessionStatus.converged_cluster,
    )
    db_session.add(session)
    await db_session.flush()

    # 5. Answer the question (exhausting the budget of 3 resolver questions)
    turn = await cluster_resolver_service.resolve_cluster_turn(
        assessment.id,
        q.id,
        0,  # select option 0
        AgeGroup.senior,
        db_session,
    )

    # 6. Verify that it was not declared single, status remains converged_cluster,
    # and decision is reveal_cluster.
    await db_session.refresh(session)
    assert session.resolve_step == 3
    assert session.status == SessionStatus.converged_cluster
    assert turn.decision.status == "reveal_cluster"
