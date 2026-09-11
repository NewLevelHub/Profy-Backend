"""PRO-262 §12/§13: admin list rows must be distinguishable without opening
each one. Before this, a page of question pairs was 20 rows of
"Пара #12 · RIASEC · Junior" and the frontend had to fetch every row's detail
just to render a label (docs/admin-backend-requests-pro-242.md)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.direction import Direction
from app.models.motivation import MotivationCategory
from app.models.motivation_pair import MotivationPair
from app.models.profile import AgeGroup
from app.models.program import Program
from app.models.question import Question, QuestionInstrument
from app.models.question_pair import QuestionPair
from app.models.university import University
from app.services import admin_content_service, admin_university_service


async def _question(db: AsyncSession, *, text: str, short_text: str | None = None) -> Question:
    question = Question(
        instrument=QuestionInstrument.big_five,
        text=text,
        short_text=short_text,
        order=0,
        age_tier=AgeGroup.junior,
    )
    db.add(question)
    await db.commit()
    await db.refresh(question)
    return question


async def _pair(db: AsyncSession, q_a: Question, q_b: Question, **kwargs) -> QuestionPair:
    pair = QuestionPair(
        instrument=QuestionInstrument.big_five,
        age_tier=AgeGroup.junior,
        pair_index=abs(hash(uuid.uuid4())) % 100_000,
        question_a_id=q_a.id,
        question_b_id=q_b.id,
        **kwargs,
    )
    db.add(pair)
    await db.commit()
    await db.refresh(pair)
    return pair


def _find(items, row_id):
    match = [i for i in items if i.id == row_id]
    assert match, f"row {row_id} not in the returned page of {len(items)}"
    return match[0]


# --- Question pairs ---------------------------------------------------------


async def test_pair_list_prefers_option_override_over_linked_question(
    db_session: AsyncSession,
) -> None:
    q_a = await _question(db_session, text="Длинное утверждение A", short_text="Коротко A")
    q_b = await _question(db_session, text="Длинное утверждение B", short_text="Коротко B")
    pair = await _pair(
        db_session, q_a, q_b, frame="На перемене", option_a_text="Чинить самокат"
    )

    result = await admin_content_service.list_question_pairs(db_session, limit=100)
    item = _find(result.items, pair.id)

    assert item.frame == "На перемене"
    assert item.option_a_text == "Чинить самокат"  # override wins
    assert item.option_b_text == "Коротко B"  # no override -> question.short_text


async def test_pair_list_falls_back_to_full_text_when_no_short_text(
    db_session: AsyncSession,
) -> None:
    """Same chain question_pair_service._to_option() uses: override, then
    short_text, then text. A middle-tier question has no short_text."""
    q_a = await _question(db_session, text="Полный текст A")
    q_b = await _question(db_session, text="Полный текст B")
    pair = await _pair(db_session, q_a, q_b)

    result = await admin_content_service.list_question_pairs(db_session, limit=100)
    item = _find(result.items, pair.id)

    assert item.option_a_text == "Полный текст A"
    assert item.option_b_text == "Полный текст B"


async def test_pair_detail_inlines_linked_questions(db_session: AsyncSession) -> None:
    q_a = await _question(db_session, text="Утверждение A", short_text="Коротко A")
    q_b = await _question(db_session, text="Утверждение B")
    pair = await _pair(db_session, q_a, q_b, option_a_text="Своя формулировка")

    detail = await admin_content_service.get_question_pair_detail(db_session, pair.id)

    # Detail keeps the RAW override (null means "falls back"), unlike the list.
    assert detail.option_a_text == "Своя формулировка"
    assert detail.option_b_text is None
    assert detail.question_a.text == "Утверждение A"
    assert detail.question_a.short_text == "Коротко A"
    assert detail.question_b.short_text is None


# --- Motivation pairs -------------------------------------------------------


async def test_motivation_pair_list_carries_texts(db_session: AsyncSession) -> None:
    """category_a always equals category_b on these rows (both poles of one
    category), so the categories cannot tell two rows apart at all."""
    pair = MotivationPair(
        pair_index=abs(hash(uuid.uuid4())) % 100_000,
        category_a=MotivationCategory.challenge,
        category_b=MotivationCategory.challenge,
        text_a="Одни ребята любят сложные задачи",
        text_b="Другие выбирают задачи полегче",
    )
    db_session.add(pair)
    await db_session.commit()

    result = await admin_content_service.list_motivation_pairs(db_session, limit=100)
    item = _find(result.items, pair.id)

    assert item.text_a == "Одни ребята любят сложные задачи"
    assert item.text_b == "Другие выбирают задачи полегче"


# --- Directions -------------------------------------------------------------


async def test_direction_list_reports_program_count_and_catalog_gaps(
    db_session: AsyncSession,
) -> None:
    university = University(name=f"Uni {uuid.uuid4()}", country="KZ", city="Almaty")
    direction = Direction(
        name=f"Направление {uuid.uuid4()}",
        slug=f"dir-{uuid.uuid4()}",
        holland_code="RIS",
        description="Есть описание",
        professions=[],  # the field that is empty on all 92 rows today
        skills_needed=["навык"],
        subjects_to_develop=["предмет"],
        first_steps=["шаг"],
    )
    db_session.add_all([university, direction])
    await db_session.commit()

    program = Program(
        university_id=university.id,
        name=f"Program {uuid.uuid4()}",
        language="Русский",
    )
    program.directions = [direction]
    db_session.add(program)
    await db_session.commit()

    result = await admin_content_service.list_directions(db_session, limit=100)
    item = _find(result.items, direction.id)

    assert item.programs_count == 1
    assert item.empty_catalog_fields == ["professions"]
    assert item.catalog_filled is False


async def test_direction_detail_lists_linked_programs(db_session: AsyncSession) -> None:
    university = University(name=f"Uni {uuid.uuid4()}", country="KZ", city="Almaty")
    direction = Direction(
        name=f"Направление {uuid.uuid4()}",
        slug=f"dir-{uuid.uuid4()}",
        holland_code="RIS",
    )
    db_session.add_all([university, direction])
    await db_session.commit()

    program = Program(
        university_id=university.id,
        name="Компьютерные науки",
        language="Русский",
    )
    program.directions = [direction]
    db_session.add(program)
    await db_session.commit()

    detail = await admin_content_service.get_direction_detail(db_session, direction.id)

    assert [p.name for p in detail.programs] == ["Компьютерные науки"]
    assert detail.programs[0].university_name == university.name


# --- Universities -----------------------------------------------------------


async def test_university_list_carries_ranking_label(db_session: AsyncSession) -> None:
    """`ranking` mixes a QS world position with a national tier in one column,
    so the number alone is not comparable between rows — the label says which
    scale it came from."""
    university = University(
        name=f"Uni {uuid.uuid4()}",
        country="KZ",
        city="Almaty",
        ranking=28,
        ranking_label="#28 (QS World)",
    )
    db_session.add(university)
    await db_session.commit()

    result = await admin_university_service.list_universities(
        db_session, limit=100, search=university.name
    )
    item = _find(result.items, university.id)

    assert item.ranking == 28
    assert item.ranking_label == "#28 (QS World)"
