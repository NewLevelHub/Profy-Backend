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
    locale: str | None = None,
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
    if locale:
        filters.append(Question.locale == locale)

    total, rows = await _count_and_paginate(
        db, Question, filters, (Question.instrument.asc(), Question.order.asc(), Question.locale.asc()), page, limit
    )

    items = [
        AdminQuestionListItem(
            id=q.id,
            locale=q.locale,
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
    locale: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> AdminQuestionPairListResponse:
    filters = []
    if instrument:
        filters.append(QuestionPair.instrument == instrument)
    if age_tier:
        filters.append(QuestionPair.age_tier == age_tier)
    if locale:
        filters.append(QuestionPair.locale == locale)

    total, rows = await _count_and_paginate(
        db, QuestionPair, filters, (QuestionPair.instrument.asc(), QuestionPair.pair_index.asc(), QuestionPair.locale.asc()), page, limit
    )

    items = [
        AdminQuestionPairListItem(
            id=p.id,
            locale=p.locale,
            instrument=p.instrument,
            age_tier=p.age_tier,
            pair_index=p.pair_index,
            has_overrides=has_overrides(p),
        )
        for p in rows
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
    locale: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> AdminMotivationStatementListResponse:
    filters = []
    if locale:
        filters.append(MotivationStatement.locale == locale)

    total, rows = await _count_and_paginate(
        db,
        MotivationStatement,
        filters,
        (MotivationStatement.triplet_index.asc(), MotivationStatement.order.asc(), MotivationStatement.locale.asc()),
        page,
        limit,
    )

    items = [
        AdminMotivationStatementListItem(
            id=s.id,
            locale=s.locale,
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
    locale: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> AdminMotivationPairListResponse:
    filters = []
    if locale:
        filters.append(MotivationPair.locale == locale)

    total, rows = await _count_and_paginate(
        db, MotivationPair, filters, (MotivationPair.pair_index.asc(), MotivationPair.locale.asc()), page, limit
    )

    items = [
        AdminMotivationPairListItem(
            id=p.id,
            locale=p.locale,
            pair_index=p.pair_index,
            category_a=p.category_a,
            category_b=p.category_b,
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


async def list_directions(
    db: AsyncSession,
    *,
    search: str | None = None,
    locale: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> AdminDirectionListResponse:
    filters = []
    if search:
        filters.append(Direction.name.ilike(f"%{search.strip()}%"))
    if locale:
        filters.append(Direction.locale == locale)

    total, rows = await _count_and_paginate(db, Direction, filters, (Direction.name.asc(), Direction.locale.asc()), page, limit)

    items = [
        AdminDirectionListItem(
            id=d.id,
            locale=d.locale,
            name=d.name,
            slug=d.slug,
            holland_code=d.holland_code,
            has_overrides=has_overrides(d),
        )
        for d in rows
    ]

    return AdminDirectionListResponse(items=items, total=total, page=page, limit=limit)


async def get_direction_detail(db: AsyncSession, direction_id: uuid.UUID) -> Direction | None:
    return await _get_by_id(db, Direction, direction_id)


async def update_direction(
    db: AsyncSession, direction_id: uuid.UUID, data: AdminDirectionUpdateRequest
) -> Direction:
    return await _update_by_id(db, Direction, direction_id, data, "Direction not found")
