import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.direction import Direction
from app.models.motivation import MotivationStatement
from app.models.motivation_pair import MotivationPair
from app.models.profile import AgeGroup
from app.models.program import Program, program_directions
from app.models.question import Question, QuestionInstrument
from app.models.question_pair import QuestionPair
from app.models.university import University
from app.schemas.admin_content import (
    AdminDirectionDetail,
    AdminDirectionListItem,
    AdminDirectionListResponse,
    AdminDirectionProgram,
    AdminDirectionUpdateRequest,
    AdminLinkedQuestion,
    AdminMotivationPairListItem,
    AdminMotivationPairListResponse,
    AdminMotivationPairUpdateRequest,
    AdminMotivationStatementListItem,
    AdminMotivationStatementListResponse,
    AdminMotivationStatementUpdateRequest,
    AdminQuestionListItem,
    AdminQuestionListResponse,
    AdminQuestionPairDetail,
    AdminQuestionPairListItem,
    AdminQuestionPairListResponse,
    AdminQuestionPairUpdateRequest,
    AdminQuestionUpdateRequest,
)
from app.services.admin_lock import AdminOverrideValidationError, apply_overrides, has_overrides


async def _get_by_id(db: AsyncSession, model, row_id: uuid.UUID):
    """Shared get-by-id body for all 5 question-bank content types below —
    the get_X_detail/update_X pairs only ever differ by model class and
    not-found message, so that's the only thing each caller supplies."""
    result = await db.execute(select(model).where(model.id == row_id))
    return result.scalar_one_or_none()


async def _update_by_id(
    db: AsyncSession, model, row_id: uuid.UUID, data, not_found_msg: str, validate=None
):
    row = await _get_by_id(db, model, row_id)
    if row is None:
        raise ValueError(not_found_msg)

    updates = data.model_dump(exclude_unset=True)
    if validate is not None:
        validate(row, updates)
    apply_overrides(row, updates)
    await db.commit()
    await db.refresh(row)
    return row


# A Question's own-instrument taxonomy field (riasec_type/bigfive_domain/
# mi_category) is nullable at the DB level only because the three
# instruments share one table — each is null for the OTHER two instruments'
# rows, never for its own. riasec_service.py/bigfive_service.py/mi_service.py
# all do `{t.value: c for t, c in ...}` after grouping by that column, which
# crashes with AttributeError on a None key. AdminQuestionUpdateRequest's
# fields are typed `| None` only so PATCHing an unrelated field doesn't force
# resending them (exclude_unset) — an explicit null must still be rejected.
_INSTRUMENT_TYPE_FIELD = {
    QuestionInstrument.riasec: "riasec_type",
    QuestionInstrument.big_five: "bigfive_domain",
    QuestionInstrument.mi: "mi_category",
}


def _validate_question_update(row: Question, updates: dict) -> None:
    type_field = _INSTRUMENT_TYPE_FIELD.get(row.instrument)
    if type_field and type_field in updates and updates[type_field] is None:
        raise AdminOverrideValidationError(
            f"{type_field} cannot be null on a {row.instrument.value} question — "
            "scoring groups responses by this field for every student."
        )


def _effective_option_text(override: str | None, question: Question | None) -> str:
    """The text a student actually sees for one side of a forced-choice pair.
    Mirrors question_pair_service._to_option() exactly — if the two ever
    disagree, the admin list stops showing what the test shows, which is the
    whole point of surfacing it. `question` is None only if the FK row went
    missing, which the ON DELETE CASCADE makes unreachable in practice."""
    if override:
        return override
    if question is None:
        return ""
    return question.short_text or question.text


async def _load_questions_by_id(
    db: AsyncSession, question_ids: set[uuid.UUID]
) -> dict[uuid.UUID, Question]:
    """One batched SELECT for every question referenced by a page of pairs —
    the alternative the frontend had to use (a detail request per row) is the
    N+1 this whole change exists to remove."""
    if not question_ids:
        return {}
    result = await db.execute(select(Question).where(Question.id.in_(question_ids)))
    return {q.id: q for q in result.scalars().all()}


async def _count_and_paginate(db: AsyncSession, model, filters: list, order_by: tuple, page: int, limit: int):
    """Shared count-then-paginate body for all 5 list_X functions below — only
    the model, filters, and ordering differ per content type."""
    total_result = await db.execute(select(func.count()).select_from(model).where(*filters))
    total = total_result.scalar_one()

    query = select(model).where(*filters).order_by(*order_by).offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    return total, result.scalars().all()


# --- Questions ---


async def list_questions(
    db: AsyncSession,
    *,
    instrument: QuestionInstrument | None = None,
    age_tier: AgeGroup | None = None,
    search: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> AdminQuestionListResponse:
    filters = []
    if instrument:
        filters.append(Question.instrument == instrument)
    if age_tier:
        filters.append(Question.age_tier == age_tier)
    if search:
        filters.append(Question.text.ilike(f"%{search.strip()}%"))

    total, rows = await _count_and_paginate(
        db, Question, filters, (Question.instrument.asc(), Question.order.asc()), page, limit
    )

    items = [
        AdminQuestionListItem(
            id=q.id,
            instrument=q.instrument,
            text=q.text,
            order=q.order,
            age_tier=q.age_tier,
            riasec_type=q.riasec_type,
            bigfive_domain=q.bigfive_domain,
            mi_category=q.mi_category,
            has_overrides=has_overrides(q),
        )
        for q in rows
    ]

    return AdminQuestionListResponse(items=items, total=total, page=page, limit=limit)


async def get_question_detail(db: AsyncSession, question_id: uuid.UUID) -> Question | None:
    return await _get_by_id(db, Question, question_id)


async def update_question(
    db: AsyncSession, question_id: uuid.UUID, data: AdminQuestionUpdateRequest
) -> Question:
    return await _update_by_id(
        db, Question, question_id, data, "Question not found", validate=_validate_question_update
    )


# --- Question pairs ---


async def list_question_pairs(
    db: AsyncSession,
    *,
    instrument: QuestionInstrument | None = None,
    age_tier: AgeGroup | None = None,
    page: int = 1,
    limit: int = 20,
) -> AdminQuestionPairListResponse:
    filters = []
    if instrument:
        filters.append(QuestionPair.instrument == instrument)
    if age_tier:
        filters.append(QuestionPair.age_tier == age_tier)

    total, rows = await _count_and_paginate(
        db, QuestionPair, filters, (QuestionPair.instrument.asc(), QuestionPair.pair_index.asc()), page, limit
    )

    questions = await _load_questions_by_id(
        db, {p.question_a_id for p in rows} | {p.question_b_id for p in rows}
    )

    items = [
        AdminQuestionPairListItem(
            id=p.id,
            instrument=p.instrument,
            age_tier=p.age_tier,
            pair_index=p.pair_index,
            frame=p.frame,
            option_a_text=_effective_option_text(p.option_a_text, questions.get(p.question_a_id)),
            option_b_text=_effective_option_text(p.option_b_text, questions.get(p.question_b_id)),
            has_overrides=has_overrides(p),
        )
        for p in rows
    ]

    return AdminQuestionPairListResponse(items=items, total=total, page=page, limit=limit)


async def _build_pair_detail(db: AsyncSession, pair: QuestionPair) -> AdminQuestionPairDetail:
    """Detail keeps the raw override columns (null = "falls back") and adds the
    two linked questions, so the form can show what an empty override resolves
    to without the caller fetching each question itself."""
    questions = await _load_questions_by_id(db, {pair.question_a_id, pair.question_b_id})
    detail = AdminQuestionPairDetail.model_validate(pair)
    detail.question_a = _linked_question(questions.get(pair.question_a_id))
    detail.question_b = _linked_question(questions.get(pair.question_b_id))
    return detail


def _linked_question(question: Question | None) -> AdminLinkedQuestion | None:
    return None if question is None else AdminLinkedQuestion.model_validate(question)


async def get_question_pair_detail(
    db: AsyncSession, pair_id: uuid.UUID
) -> AdminQuestionPairDetail | None:
    pair = await _get_by_id(db, QuestionPair, pair_id)
    return None if pair is None else await _build_pair_detail(db, pair)


async def update_question_pair(
    db: AsyncSession, pair_id: uuid.UUID, data: AdminQuestionPairUpdateRequest
) -> AdminQuestionPairDetail:
    pair = await _update_by_id(db, QuestionPair, pair_id, data, "Question pair not found")
    return await _build_pair_detail(db, pair)


# --- Motivation statements ---


async def list_motivation_statements(
    db: AsyncSession,
    *,
    page: int = 1,
    limit: int = 20,
) -> AdminMotivationStatementListResponse:
    total, rows = await _count_and_paginate(
        db,
        MotivationStatement,
        [],
        (MotivationStatement.triplet_index.asc(), MotivationStatement.order.asc()),
        page,
        limit,
    )

    items = [
        AdminMotivationStatementListItem(
            id=s.id,
            triplet_index=s.triplet_index,
            order=s.order,
            category=s.category,
            text=s.text,
            has_overrides=has_overrides(s),
        )
        for s in rows
    ]

    return AdminMotivationStatementListResponse(items=items, total=total, page=page, limit=limit)


async def get_motivation_statement_detail(
    db: AsyncSession, statement_id: uuid.UUID
) -> MotivationStatement | None:
    return await _get_by_id(db, MotivationStatement, statement_id)


async def update_motivation_statement(
    db: AsyncSession, statement_id: uuid.UUID, data: AdminMotivationStatementUpdateRequest
) -> MotivationStatement:
    return await _update_by_id(
        db, MotivationStatement, statement_id, data, "Motivation statement not found"
    )


# --- Motivation pairs ---


async def list_motivation_pairs(
    db: AsyncSession,
    *,
    page: int = 1,
    limit: int = 20,
) -> AdminMotivationPairListResponse:
    total, rows = await _count_and_paginate(
        db, MotivationPair, [], (MotivationPair.pair_index.asc(),), page, limit
    )

    items = [
        AdminMotivationPairListItem(
            id=p.id,
            pair_index=p.pair_index,
            category_a=p.category_a,
            category_b=p.category_b,
            text_a=p.text_a,
            text_b=p.text_b,
            has_overrides=has_overrides(p),
        )
        for p in rows
    ]

    return AdminMotivationPairListResponse(items=items, total=total, page=page, limit=limit)


async def get_motivation_pair_detail(db: AsyncSession, pair_id: uuid.UUID) -> MotivationPair | None:
    return await _get_by_id(db, MotivationPair, pair_id)


async def update_motivation_pair(
    db: AsyncSession, pair_id: uuid.UUID, data: AdminMotivationPairUpdateRequest
) -> MotivationPair:
    return await _update_by_id(db, MotivationPair, pair_id, data, "Motivation pair not found")


# --- Directions ---


# The descriptive half of a Direction — everything except name/slug/
# holland_code, which the RIASEC seed always fills. These five are seeded
# empty and filled by a later content pass, so "how much of the catalog is
# actually written" is a per-field question, not a per-row one. All five feed
# report_service and the two direction LLM prompts; an empty one silently
# degrades those, which is why the gap is reported instead of rendered blank.
_DIRECTION_CATALOG_FIELDS = (
    "description",
    "professions",
    "skills_needed",
    "subjects_to_develop",
    "first_steps",
)


def _empty_catalog_fields(direction: Direction) -> list[str]:
    return [f for f in _DIRECTION_CATALOG_FIELDS if not getattr(direction, f)]


async def _programs_count_by_direction(
    db: AsyncSession, direction_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """Counts straight off the `program_directions` association — one grouped
    query for the whole page rather than a correlated subquery per row."""
    if not direction_ids:
        return {}
    result = await db.execute(
        select(program_directions.c.direction_id, func.count())
        .where(program_directions.c.direction_id.in_(direction_ids))
        .group_by(program_directions.c.direction_id)
    )
    return {direction_id: count for direction_id, count in result.all()}


async def list_directions(
    db: AsyncSession,
    *,
    search: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> AdminDirectionListResponse:
    filters = []
    if search:
        filters.append(Direction.name.ilike(f"%{search.strip()}%"))

    total, rows = await _count_and_paginate(db, Direction, filters, (Direction.name.asc(),), page, limit)

    counts = await _programs_count_by_direction(db, [d.id for d in rows])

    items = []
    for d in rows:
        empty_fields = _empty_catalog_fields(d)
        items.append(
            AdminDirectionListItem(
                id=d.id,
                name=d.name,
                slug=d.slug,
                holland_code=d.holland_code,
                programs_count=counts.get(d.id, 0),
                catalog_filled=not empty_fields,
                empty_catalog_fields=empty_fields,
                has_overrides=has_overrides(d),
            )
        )

    return AdminDirectionListResponse(items=items, total=total, page=page, limit=limit)


async def _build_direction_detail(db: AsyncSession, direction: Direction) -> AdminDirectionDetail:
    result = await db.execute(
        select(Program.id, Program.name, University.id, University.name)
        .join(program_directions, program_directions.c.program_id == Program.id)
        .join(University, Program.university_id == University.id)
        .where(program_directions.c.direction_id == direction.id)
        .order_by(University.name.asc(), Program.name.asc())
    )
    detail = AdminDirectionDetail.model_validate(direction)
    detail.programs = [
        AdminDirectionProgram(
            id=program_id,
            name=program_name,
            university_id=university_id,
            university_name=university_name,
        )
        for program_id, program_name, university_id, university_name in result.all()
    ]
    return detail


async def get_direction_detail(
    db: AsyncSession, direction_id: uuid.UUID
) -> AdminDirectionDetail | None:
    direction = await _get_by_id(db, Direction, direction_id)
    return None if direction is None else await _build_direction_detail(db, direction)


async def update_direction(
    db: AsyncSession, direction_id: uuid.UUID, data: AdminDirectionUpdateRequest
) -> AdminDirectionDetail:
    direction = await _update_by_id(db, Direction, direction_id, data, "Direction not found")
    return await _build_direction_detail(db, direction)
