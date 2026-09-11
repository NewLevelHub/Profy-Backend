"""PRO-262 §1/§2/§3: one sort/search/filter contract across every admin list.

Before this, no list endpoint accepted `sort`, four had no `search` at all,
and /admin/feedback — an entire screen that exists to answer "show me the 1-2
scores and let me read the comments" — took only page and limit. The frontend
compensated by downloading whole tables and filtering them client-side
(docs/admin-backend-requests-pro-242.md §3, §12).
"""

import uuid

import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, AssessmentGoal, AssessmentStatus
from app.models.direction import Direction
from app.models.motivation import MotivationCategory, MotivationStatement
from app.models.product_feedback import ProductFeedback
from app.models.profile import AgeGroup, Profile
from app.models.program import Program
from app.models.question import Question, QuestionInstrument
from app.models.question_pair import QuestionPair
from app.models.university import University
from app.models.user import User, UserRole
from app.services import admin_content_service, admin_service, admin_university_service, auth_service
from app.services.admin_listing import AdminSortFieldError

import pytest


@pytest_asyncio.fixture
async def admin_headers(db_session: AsyncSession) -> dict[str, str]:
    admin = User(
        email=f"{uuid.uuid4()}@admin.test",
        hashed_password="x",
        is_active=True,
        is_verified=True,
        role=UserRole.admin,
    )
    db_session.add(admin)
    await db_session.flush()
    return {"Authorization": f"Bearer {auth_service.create_jwt_token(admin.id)}"}


def _marker() -> str:
    """Seeded content shares these tables, so every test isolates its own rows
    by filtering on a value nothing else can have."""
    return f"pro262-{uuid.uuid4()}"


async def _university(db: AsyncSession, name: str, **kwargs) -> University:
    university = University(
        name=name,
        country=kwargs.pop("country", "Казахстан"),
        city=kwargs.pop("city", "Алматы"),
        **kwargs,
    )
    db.add(university)
    await db.flush()
    return university


# --- the contract itself ----------------------------------------------------


async def test_unknown_sort_field_is_422_naming_the_allowed_set(
    client: httpx.AsyncClient, admin_headers: dict[str, str]
) -> None:
    """Silently falling back to the default order would be indistinguishable
    from a column whose sort does nothing."""
    response = await client.get(
        "/api/v1/admin/questions", params={"sort": "not_a_column"}, headers=admin_headers
    )

    assert response.status_code == 422
    body = response.json()
    assert "not_a_column" in body["detail"]
    assert "order" in body["allowed_sort_fields"]


async def test_service_raises_for_unknown_sort_field(db_session: AsyncSession) -> None:
    with pytest.raises(AdminSortFieldError):
        await admin_content_service.list_questions(db_session, sort="nope")


async def test_sort_direction_is_honoured(db_session: AsyncSession) -> None:
    marker = _marker()
    for suffix in ("b", "a", "c"):
        await _university(db_session, f"{marker} {suffix}")

    ascending = await admin_university_service.list_universities(
        db_session, search=marker, sort="name", order="asc", limit=100
    )
    descending = await admin_university_service.list_universities(
        db_session, search=marker, sort="name", order="desc", limit=100
    )

    assert [i.name[-1] for i in ascending.items] == ["a", "b", "c"]
    assert [i.name[-1] for i in descending.items] == ["c", "b", "a"]


async def test_nulls_sort_last_even_on_desc(db_session: AsyncSession) -> None:
    """Postgres puts NULLs FIRST on DESC by default, which would open "sort by
    ranking, highest first" on the rows that have no ranking at all."""
    marker = _marker()
    await _university(db_session, f"{marker} unranked", ranking=None)
    await _university(db_session, f"{marker} ranked", ranking=28)

    result = await admin_university_service.list_universities(
        db_session, search=marker, sort="ranking", order="desc", limit=100
    )

    assert [i.ranking for i in result.items] == [28, None]


async def test_pagination_does_not_repeat_rows_when_the_sort_key_ties(
    db_session: AsyncSession,
) -> None:
    """Every row here has the same `country`, so without the unique tiebreaker
    the order between them is undefined and OFFSET can hand back the same row
    on two different pages."""
    marker = _marker()
    for index in range(6):
        await _university(db_session, f"{marker} {index}", country=marker)

    seen = []
    for page in (1, 2, 3):
        result = await admin_university_service.list_universities(
            db_session, country=marker, sort="country", order="asc", page=page, limit=2
        )
        seen.extend(i.id for i in result.items)

    assert len(seen) == len(set(seen)) == 6


# --- universities: search and filters ---------------------------------------


async def test_university_search_matches_city_short_name_and_alias(
    db_session: AsyncSession,
) -> None:
    """Name-only search was why a university could not be found by the city it
    sits in, or by the abbreviation everyone actually uses for it."""
    marker = _marker()
    by_city = await _university(db_session, f"Университет {uuid.uuid4()}", city=marker)
    by_alias = await _university(
        db_session, f"Университет {uuid.uuid4()}", aliases=[marker, "прочее"]
    )
    by_short = await _university(
        db_session, f"Университет {uuid.uuid4()}", short_name=marker
    )

    result = await admin_university_service.list_universities(
        db_session, search=marker, limit=100
    )

    assert {i.id for i in result.items} == {by_city.id, by_alias.id, by_short.id}


async def test_university_country_and_has_ranking_filters(db_session: AsyncSession) -> None:
    marker = _marker()
    ranked = await _university(db_session, f"{marker} ranked", country=marker, ranking=10)
    await _university(db_session, f"{marker} unranked", country=marker)

    with_ranking = await admin_university_service.list_universities(
        db_session, country=marker, has_ranking=True, limit=100
    )
    without_ranking = await admin_university_service.list_universities(
        db_session, country=marker, has_ranking=False, limit=100
    )

    assert [i.id for i in with_ranking.items] == [ranked.id]
    assert with_ranking.total == 1
    assert len(without_ranking.items) == 1


async def test_university_sort_by_programs_count(db_session: AsyncSession) -> None:
    """programs_count is a COUNT(), not a column — it can only be ordered by
    the same aggregate the SELECT already computes."""
    marker = _marker()
    empty = await _university(db_session, f"{marker} empty", country=marker)
    busy = await _university(db_session, f"{marker} busy", country=marker)
    db_session.add_all(
        [
            Program(university_id=busy.id, name=f"P{i} {uuid.uuid4()}", language="ru")
            for i in range(2)
        ]
    )
    await db_session.flush()

    result = await admin_university_service.list_universities(
        db_session, country=marker, sort="programs_count", order="desc", limit=100
    )

    assert [i.id for i in result.items] == [busy.id, empty.id]
    assert [i.programs_count for i in result.items] == [2, 0]


# --- users ------------------------------------------------------------------


async def _user_with_profile(
    db: AsyncSession, marker: str, age_group: AgeGroup, statuses: list[AssessmentStatus]
) -> User:
    user = User(
        email=f"{uuid.uuid4()}-{marker}@example.test",
        hashed_password="x",
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    await db.flush()

    profile = Profile(
        user_id=user.id,
        name="Тест",
        age={AgeGroup.junior: 8, AgeGroup.middle: 12, AgeGroup.senior: 16}[age_group],
        grade=5,
        city="Алматы",
        country="Казахстан",
        language="ru",
        age_group=age_group,
    )
    db.add(profile)
    await db.flush()

    for status in statuses:
        db.add(Assessment(profile_id=profile.id, goal=AssessmentGoal.explore, status=status))
    await db.flush()
    return user


async def test_users_sort_by_joined_column_together_with_an_assessment_filter(
    db_session: AsyncSession,
) -> None:
    """The one combination that Postgres rejects outright if built naively:
    filtering by assessment status forces SELECT DISTINCT, and DISTINCT
    requires every ORDER BY expression to be in the select list — which
    Profile.age_group is not, since the query selects User."""
    marker = _marker()
    senior = await _user_with_profile(
        db_session, marker, AgeGroup.senior, [AssessmentStatus.completed]
    )
    junior = await _user_with_profile(
        db_session, marker, AgeGroup.junior, [AssessmentStatus.completed, AssessmentStatus.completed]
    )

    result = await admin_service.list_users(
        db_session,
        search=marker,
        status=AssessmentStatus.completed,
        sort="age_group",
        order="asc",
        limit=100,
    )

    assert [i.id for i in result.items] == [junior.id, senior.id]
    # two matching assessments on one user must still count as one user
    assert result.total == 2


async def test_users_sort_by_latest_assessment_status(db_session: AsyncSession) -> None:
    """`latest_assessment_status` is not a column — the sort has to agree with
    the value shown in the row, which is the newest assessment's status."""
    marker = _marker()
    completed = await _user_with_profile(
        db_session, marker, AgeGroup.senior, [AssessmentStatus.completed]
    )
    in_progress = await _user_with_profile(
        db_session, marker, AgeGroup.senior, [AssessmentStatus.in_progress]
    )

    result = await admin_service.list_users(
        db_session, search=marker, sort="latest_assessment_status", order="asc", limit=100
    )

    assert [i.id for i in result.items] == [in_progress.id, completed.id]
    assert [i.latest_assessment_status for i in result.items] == ["in_progress", "completed"]


# --- feedback ---------------------------------------------------------------


async def _feedback(
    db: AsyncSession,
    marker: str,
    *,
    score: int,
    comment: str | None = None,
    age_group: AgeGroup | None = None,
) -> ProductFeedback:
    user = User(
        email=f"{uuid.uuid4()}@example.test", hashed_password="x", is_active=True, is_verified=True
    )
    db.add(user)
    await db.flush()

    assessment_id = None
    if age_group is not None:
        profile = Profile(
            user_id=user.id,
            name="Тест",
            age=16,
            grade=5,
            city="Алматы",
            country="Казахстан",
            language="ru",
            age_group=age_group,
        )
        db.add(profile)
        await db.flush()
        assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
        db.add(assessment)
        await db.flush()
        assessment_id = assessment.id

    feedback = ProductFeedback(
        user_id=user.id,
        assessment_id=assessment_id,
        relevance_score=score,
        helpful_sections=[marker],
        comment=comment,
    )
    db.add(feedback)
    await db.flush()
    return feedback


async def test_feedback_score_range_and_comment_filters(db_session: AsyncSession) -> None:
    """The negative-feedback slice this screen exists for: scores 1-2 that
    actually have something written in them."""
    marker = _marker()
    bad_with_comment = await _feedback(db_session, marker, score=1, comment="не понял выводы")
    await _feedback(db_session, marker, score=2, comment="   ")  # blank = nothing to read
    await _feedback(db_session, marker, score=5, comment="всё отлично")

    result = await admin_service.list_feedback(
        db_session, section=marker, score_min=1, score_max=2, has_comment=True, limit=100
    )

    assert [i.id for i in result.items] == [bad_with_comment.id]
    assert result.total == 1


async def test_feedback_comment_search_and_age_group_filter(db_session: AsyncSession) -> None:
    """age_group lives on the profile behind the assessment, so filtering by it
    joins through both — and feedback whose assessment was deleted has no
    knowable age group and must not be counted as a match."""
    marker = _marker()
    senior = await _feedback(
        db_session, marker, score=3, comment="откуда выводы", age_group=AgeGroup.senior
    )
    await _feedback(db_session, marker, score=3, comment="откуда выводы", age_group=AgeGroup.junior)
    await _feedback(db_session, marker, score=3, comment="откуда выводы")  # no assessment

    by_comment = await admin_service.list_feedback(
        db_session, section=marker, search="откуда", limit=100
    )
    by_age = await admin_service.list_feedback(
        db_session, section=marker, age_group=AgeGroup.senior, limit=100
    )

    assert by_comment.total == 3
    assert [i.id for i in by_age.items] == [senior.id]


async def test_feedback_stats_describe_the_filtered_rows(db_session: AsyncSession) -> None:
    """The summary has to follow the filter, otherwise the two numbers on the
    screen contradict each other — the reason the frontend stopped calling
    this endpoint and recomputed the summary itself."""
    marker = _marker()
    await _feedback(db_session, marker, score=1)
    await _feedback(db_session, marker, score=5)

    everything = await admin_service.get_feedback_stats(db_session, section=marker)
    negative_only = await admin_service.get_feedback_stats(
        db_session, section=marker, score_max=2
    )

    assert everything.total == 2
    assert everything.avg_relevance_score == 3.0
    assert negative_only.total == 1
    assert negative_only.avg_relevance_score == 1.0


# --- question-bank content --------------------------------------------------


async def test_has_overrides_filter_splits_edited_from_untouched(
    db_session: AsyncSession,
) -> None:
    """"Show me everything that was edited by hand" is the slice an admin wants
    before a deploy, since a resync composes overrides back over the bank."""
    marker = _marker()
    edited = Direction(
        name=f"{marker} edited", slug=f"{marker}-edited", holland_code="RIS",
        overrides={"name": f"{marker} edited"},
    )
    untouched = Direction(
        name=f"{marker} plain", slug=f"{marker}-plain", holland_code="RIS"
    )
    db_session.add_all([edited, untouched])
    await db_session.flush()

    with_overrides = await admin_content_service.list_directions(
        db_session, search=marker, has_overrides_filter=True, limit=100
    )
    without_overrides = await admin_content_service.list_directions(
        db_session, search=marker, has_overrides_filter=False, limit=100
    )

    assert [i.id for i in with_overrides.items] == [edited.id]
    assert [i.id for i in without_overrides.items] == [untouched.id]


async def test_direction_catalog_filled_filter_matches_the_row_flag(
    db_session: AsyncSession,
) -> None:
    """The SQL filter and the per-row `catalog_filled` flag are computed in two
    different places; if they ever disagree the list contradicts itself."""
    marker = _marker()
    full = Direction(
        name=f"{marker} full", slug=f"{marker}-full", holland_code="RIS",
        description="описание", professions=["p"], skills_needed=["s"],
        subjects_to_develop=["s"], first_steps=["f"],
    )
    partial = Direction(
        name=f"{marker} partial", slug=f"{marker}-partial", holland_code="RIS",
        description="описание", professions=[], skills_needed=["s"],
        subjects_to_develop=["s"], first_steps=["f"],
    )
    db_session.add_all([full, partial])
    await db_session.flush()

    filled = await admin_content_service.list_directions(
        db_session, search=marker, catalog_filled=True, limit=100
    )
    unfilled = await admin_content_service.list_directions(
        db_session, search=marker, catalog_filled=False, limit=100
    )

    assert [i.id for i in filled.items] == [full.id]
    assert filled.items[0].catalog_filled is True
    assert [i.id for i in unfilled.items] == [partial.id]
    assert unfilled.items[0].empty_catalog_fields == ["professions"]


async def test_question_pair_search_matches_the_text_a_student_sees(
    db_session: AsyncSession,
) -> None:
    """Matching only the override columns would skip every junior pair, since
    those leave both overrides null and fall back to the linked question."""
    marker = _marker()
    question_a = Question(
        instrument=QuestionInstrument.big_five,
        text=f"{marker} чинить самокат",
        order=0,
        age_tier=AgeGroup.junior,
    )
    question_b = Question(
        instrument=QuestionInstrument.big_five, text="играть в салки", order=0,
        age_tier=AgeGroup.junior,
    )
    db_session.add_all([question_a, question_b])
    await db_session.flush()

    fallback_pair = QuestionPair(
        instrument=QuestionInstrument.big_five, age_tier=AgeGroup.junior,
        pair_index=900_001, question_a_id=question_a.id, question_b_id=question_b.id,
    )
    overridden_pair = QuestionPair(
        instrument=QuestionInstrument.big_five, age_tier=AgeGroup.junior,
        pair_index=900_002, question_a_id=question_b.id, question_b_id=question_b.id,
        option_a_text=f"{marker} рисовать комикс",
    )
    db_session.add_all([fallback_pair, overridden_pair])
    await db_session.flush()

    result = await admin_content_service.list_question_pairs(
        db_session, search=marker, limit=100
    )

    assert {i.id for i in result.items} == {fallback_pair.id, overridden_pair.id}
    assert result.total == 2


async def test_question_pair_search_does_not_match_a_shadowed_fallback(
    db_session: AsyncSession,
) -> None:
    """An override replaces the question's own wording on screen, so the
    hidden fallback must not be findable — the search would otherwise return a
    row whose visible text contains nothing the admin typed."""
    marker = _marker()
    question = Question(
        instrument=QuestionInstrument.big_five,
        text=f"{marker} скрытый текст",
        order=0,
        age_tier=AgeGroup.junior,
    )
    db_session.add(question)
    await db_session.flush()

    pair = QuestionPair(
        instrument=QuestionInstrument.big_five, age_tier=AgeGroup.junior,
        pair_index=900_003, question_a_id=question.id, question_b_id=question.id,
        option_a_text="видимый текст", option_b_text="видимый текст",
    )
    db_session.add(pair)
    await db_session.flush()

    result = await admin_content_service.list_question_pairs(
        db_session, search=marker, limit=100
    )

    assert result.total == 0


async def test_motivation_statements_can_be_fetched_one_triplet_at_a_time(
    db_session: AsyncSession,
) -> None:
    """Three statements of a triplet must carry three different categories and
    nothing server-side enforces that yet — so the admin editing one needs to
    see the other two."""
    triplet_index = 900_100
    for order, category in enumerate(
        (MotivationCategory.interest, MotivationCategory.money, MotivationCategory.freedom)
    ):
        db_session.add(
            MotivationStatement(
                triplet_index=triplet_index,
                order=order,
                category=category,
                text=f"Утверждение {order}",
            )
        )
    await db_session.flush()

    result = await admin_content_service.list_motivation_statements(
        db_session, triplet_index=triplet_index, limit=100
    )

    assert result.total == 3
    assert [i.order for i in result.items] == [0, 1, 2]


# --- collation and facets ---------------------------------------------------


async def test_cyrillic_names_sort_alphabetically_not_by_byte_value(
    db_session: AsyncSession,
) -> None:
    """Postgres' default collation puts every Latin-named row ahead of every
    Cyrillic one — that is why sorting 252 universities by name used to open on
    "Aalto University" and push all 111 Kazakh ones to page six."""
    marker = _marker()
    await _university(db_session, f"{marker} Ярославский", country=marker)
    await _university(db_session, f"{marker} Zeta University", country=marker)
    await _university(db_session, f"{marker} Академия", country=marker)

    result = await admin_university_service.list_universities(
        db_session, country=marker, sort="name", order="asc", limit=100
    )

    assert [i.name.split(" ", 1)[1] for i in result.items] == [
        "Академия",
        "Ярославский",
        "Zeta University",
    ]


async def test_default_order_uses_the_same_collation(db_session: AsyncSession) -> None:
    """An unsorted list is what an admin sees first, so the default order is
    the one that mattered most in the original complaint."""
    marker = _marker()
    await _university(db_session, f"{marker} Ярославский", country=marker)
    await _university(db_session, f"{marker} Академия", country=marker)

    result = await admin_university_service.list_universities(
        db_session, country=marker, limit=100
    )

    assert [i.name.split(" ", 1)[1] for i in result.items] == ["Академия", "Ярославский"]


async def test_has_programs_filter_finds_universities_no_student_can_reach(
    db_session: AsyncSession,
) -> None:
    marker = _marker()
    empty = await _university(db_session, f"{marker} empty", country=marker)
    busy = await _university(db_session, f"{marker} busy", country=marker)
    db_session.add(Program(university_id=busy.id, name=f"P {uuid.uuid4()}", language="ru"))
    await db_session.flush()

    without = await admin_university_service.list_universities(
        db_session, country=marker, has_programs=False, limit=100
    )
    with_programs = await admin_university_service.list_universities(
        db_session, country=marker, has_programs=True, limit=100
    )

    assert [i.id for i in without.items] == [empty.id]
    assert [i.id for i in with_programs.items] == [busy.id]


async def test_country_facet_lists_options_with_their_counts(
    db_session: AsyncSession,
) -> None:
    """The country filter needs every value, which a page of 20 rows cannot
    supply — this replaces downloading the whole catalog to count them."""
    marker = _marker()
    await _university(db_session, f"{marker} a", country=marker)
    await _university(db_session, f"{marker} b", country=marker)

    countries = await admin_university_service.list_countries(db_session)
    entry = next(c for c in countries if c.country == marker)

    assert entry.universities_count == 2
    # Most-populated first, so the real catalog's countries lead the list.
    counts = [c.universities_count for c in countries]
    assert counts == sorted(counts, reverse=True)
