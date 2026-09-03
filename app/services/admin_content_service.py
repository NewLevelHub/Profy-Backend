import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.direction import Direction
from app.models.motivation import MotivationStatement
from app.models.motivation_pair import MotivationPair
from app.models.profile import AgeGroup
from app.models.question import Question, QuestionInstrument
from app.models.question_pair import QuestionPair
from app.schemas.admin_content import (
    AdminDirectionListItem,
    AdminDirectionListResponse,
    AdminDirectionUpdateRequest,
    AdminMotivationPairListItem,
    AdminMotivationPairListResponse,
    AdminMotivationPairUpdateRequest,
    AdminMotivationStatementListItem,
    AdminMotivationStatementListResponse,
    AdminMotivationStatementUpdateRequest,
    AdminQuestionListItem,
    AdminQuestionListResponse,
    AdminQuestionPairListItem,
    AdminQuestionPairListResponse,
    AdminQuestionPairUpdateRequest,
    AdminQuestionUpdateRequest,
)
from app.services.admin_lock import apply_overrides


async def _get_by_id(db: AsyncSession, model, row_id: uuid.UUID):
    """Shared get-by-id body for all 5 question-bank content types below —
    the get_X_detail/update_X pairs only ever differ by model class and
    not-found message, so that's the only thing each caller supplies."""
    result = await db.execute(select(model).where(model.id == row_id))
    return result.scalar_one_or_none()


async def _update_by_id(db: AsyncSession, model, row_id: uuid.UUID, data, not_found_msg: str):
    row = await _get_by_id(db, model, row_id)
    if row is None:
        raise ValueError(not_found_msg)

    apply_overrides(row, data.model_dump(exclude_unset=True))
    await db.commit()
    await db.refresh(row)
    return row


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

    total_result = await db.execute(select(func.count()).select_from(Question).where(*filters))
    total = total_result.scalar_one()

    query = (
        select(Question)
        .where(*filters)
        .order_by(Question.instrument.asc(), Question.order.asc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await db.execute(query)

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
            has_overrides=bool(q.overrides),
        )
        for q in result.scalars().all()
    ]

    return AdminQuestionListResponse(items=items, total=total, page=page, limit=limit)


async def get_question_detail(db: AsyncSession, question_id: uuid.UUID) -> Question | None:
    return await _get_by_id(db, Question, question_id)


async def update_question(
    db: AsyncSession, question_id: uuid.UUID, data: AdminQuestionUpdateRequest
) -> Question:
    return await _update_by_id(db, Question, question_id, data, "Question not found")


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

    total_result = await db.execute(select(func.count()).select_from(QuestionPair).where(*filters))
    total = total_result.scalar_one()

    query = (
        select(QuestionPair)
        .where(*filters)
        .order_by(QuestionPair.instrument.asc(), QuestionPair.pair_index.asc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await db.execute(query)

    items = [
        AdminQuestionPairListItem(
            id=p.id,
            instrument=p.instrument,
            age_tier=p.age_tier,
            pair_index=p.pair_index,
            has_overrides=bool(p.overrides),
        )
        for p in result.scalars().all()
    ]

    return AdminQuestionPairListResponse(items=items, total=total, page=page, limit=limit)


async def get_question_pair_detail(db: AsyncSession, pair_id: uuid.UUID) -> QuestionPair | None:
    return await _get_by_id(db, QuestionPair, pair_id)


async def update_question_pair(
    db: AsyncSession, pair_id: uuid.UUID, data: AdminQuestionPairUpdateRequest
) -> QuestionPair:
    return await _update_by_id(db, QuestionPair, pair_id, data, "Question pair not found")


# --- Motivation statements ---


async def list_motivation_statements(
    db: AsyncSession,
    *,
    page: int = 1,
    limit: int = 20,
) -> AdminMotivationStatementListResponse:
    total_result = await db.execute(select(func.count()).select_from(MotivationStatement))
    total = total_result.scalar_one()

    query = (
        select(MotivationStatement)
        .order_by(MotivationStatement.triplet_index.asc(), MotivationStatement.order.asc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await db.execute(query)

    items = [
        AdminMotivationStatementListItem(
            id=s.id,
            triplet_index=s.triplet_index,
            order=s.order,
            category=s.category,
            text=s.text,
            has_overrides=bool(s.overrides),
        )
        for s in result.scalars().all()
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
    total_result = await db.execute(select(func.count()).select_from(MotivationPair))
    total = total_result.scalar_one()

    query = (
        select(MotivationPair)
        .order_by(MotivationPair.pair_index.asc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await db.execute(query)

    items = [
        AdminMotivationPairListItem(
            id=p.id,
            pair_index=p.pair_index,
            category_a=p.category_a,
            category_b=p.category_b,
            has_overrides=bool(p.overrides),
        )
        for p in result.scalars().all()
    ]

    return AdminMotivationPairListResponse(items=items, total=total, page=page, limit=limit)


async def get_motivation_pair_detail(db: AsyncSession, pair_id: uuid.UUID) -> MotivationPair | None:
    return await _get_by_id(db, MotivationPair, pair_id)


async def update_motivation_pair(
    db: AsyncSession, pair_id: uuid.UUID, data: AdminMotivationPairUpdateRequest
) -> MotivationPair:
    return await _update_by_id(db, MotivationPair, pair_id, data, "Motivation pair not found")


# --- Directions ---


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

    total_result = await db.execute(select(func.count()).select_from(Direction).where(*filters))
    total = total_result.scalar_one()

    query = (
        select(Direction)
        .where(*filters)
        .order_by(Direction.name.asc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await db.execute(query)

    items = [
        AdminDirectionListItem(
            id=d.id,
            name=d.name,
            slug=d.slug,
            holland_code=d.holland_code,
            has_overrides=bool(d.overrides),
        )
        for d in result.scalars().all()
    ]

    return AdminDirectionListResponse(items=items, total=total, page=page, limit=limit)


async def get_direction_detail(db: AsyncSession, direction_id: uuid.UUID) -> Direction | None:
    return await _get_by_id(db, Direction, direction_id)


async def update_direction(
    db: AsyncSession, direction_id: uuid.UUID, data: AdminDirectionUpdateRequest
) -> Direction:
    return await _update_by_id(db, Direction, direction_id, data, "Direction not found")
