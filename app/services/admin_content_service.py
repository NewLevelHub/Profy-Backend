import uuid

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.direction import Direction
from app.models.motivation import MotivationCategory, MotivationStatement
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
from app.services.admin_lock import (
    AdminNothingToClearError,
    AdminOverrideValidationError,
    apply_overrides,
    clear_overrides,
    has_overrides,
)
from app.services.admin_listing import SortOrder, order_by_clause


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


async def _clear_overrides_by_id(
    db: AsyncSession, model, row_id: uuid.UUID, not_found_msg: str, field: str | None = None
):
    """Undo one override, or every override on the row when `field` is None.

    Asking to clear a field that carries no override is reported rather than
    quietly succeeding: the caller believes an edit exists there, and the only
    honest answers are "removed it" or "there wasn't one"."""
    row = await _get_by_id(db, model, row_id)
    if row is None:
        raise ValueError(not_found_msg)

    cleared = clear_overrides(row, None if field is None else [field])
    if field is not None and not cleared:
        raise AdminNothingToClearError(f"Field '{field}' is not overridden on this row")

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


def _overrides_filter(model, has_overrides_value: bool):
    """"Show me everything that was edited by hand" — the slice an admin wants
    before a deploy, since a resync composes overrides back on top of the bank
    (docs/admin-questions-content-overrides-plan.md). An untouched row holds
    an empty JSONB object, not null."""
    return model.overrides != {} if has_overrides_value else model.overrides == {}


async def _count_and_paginate(
    db: AsyncSession,
    model,
    filters: list,
    order_by: list,
    page: int,
    limit: int,
    joins: tuple = (),
):
    """Shared count-then-paginate body for all 5 list_X functions below — only
    the model, filters, joins and ordering differ per content type. `joins`
    are applied to the count query too, or a filter that lives on a joined
    table would make `total` disagree with the page it describes."""
    count_query = select(func.count()).select_from(model)
    query = select(model)
    for target, onclause in joins:
        count_query = count_query.join(target, onclause)
        query = query.join(target, onclause)

    total_result = await db.execute(count_query.where(*filters))
    total = total_result.scalar_one()

    query = query.where(*filters).order_by(*order_by).offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    return total, result.scalars().all()


# --- Questions ---


QUESTION_SORT_FIELDS = {
    "order": Question.order,
    "instrument": Question.instrument,
    "age_tier": Question.age_tier,
    "text": Question.text,
}


async def list_questions(
    db: AsyncSession,
    *,
    instrument: QuestionInstrument | None = None,
    age_tier: AgeGroup | None = None,
    search: str | None = None,
    has_overrides_filter: bool | None = None,
    sort: str | None = None,
    order: SortOrder | None = None,
    page: int = 1,
    limit: int = 20,
) -> AdminQuestionListResponse:
    filters = []
    if instrument:
        filters.append(Question.instrument == instrument)
    if age_tier:
        filters.append(Question.age_tier == age_tier)
    if search:
        like = f"%{search.strip()}%"
        filters.append(or_(Question.text.ilike(like), Question.short_text.ilike(like)))
    if has_overrides_filter is not None:
        filters.append(_overrides_filter(Question, has_overrides_filter))

    total, rows = await _count_and_paginate(
        db,
        Question,
        filters,
        order_by_clause(
            sort,
            order,
            allowed=QUESTION_SORT_FIELDS,
            default=(Question.instrument.asc(), Question.order.asc()),
            tiebreaker=Question.id.asc(),
        ),
        page,
        limit,
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


async def clear_question_overrides(
    db: AsyncSession, question_id: uuid.UUID, field: str | None = None
) -> Question:
    return await _clear_overrides_by_id(db, Question, question_id, "Question not found", field)


# --- Question pairs ---


QUESTION_PAIR_SORT_FIELDS = {
    "pair_index": QuestionPair.pair_index,
    "instrument": QuestionPair.instrument,
    "age_tier": QuestionPair.age_tier,
}


async def list_question_pairs(
    db: AsyncSession,
    *,
    instrument: QuestionInstrument | None = None,
    age_tier: AgeGroup | None = None,
    search: str | None = None,
    has_overrides_filter: bool | None = None,
    sort: str | None = None,
    order: SortOrder | None = None,
    page: int = 1,
    limit: int = 20,
) -> AdminQuestionPairListResponse:
    filters = []
    joins: tuple = ()
    if instrument:
        filters.append(QuestionPair.instrument == instrument)
    if age_tier:
        filters.append(QuestionPair.age_tier == age_tier)
    if has_overrides_filter is not None:
        filters.append(_overrides_filter(QuestionPair, has_overrides_filter))
    if search:
        # Search the text a student would actually see, which for a pair
        # without an override is the linked question's own wording — matching
        # only the override columns would silently skip every junior pair,
        # since junior pairs leave both overrides null.
        like = f"%{search.strip()}%"
        q_a = aliased(Question)
        q_b = aliased(Question)
        joins = (
            (q_a, QuestionPair.question_a_id == q_a.id),
            (q_b, QuestionPair.question_b_id == q_b.id),
        )
        filters.append(
            or_(
                QuestionPair.frame.ilike(like),
                func.coalesce(QuestionPair.option_a_text, q_a.short_text, q_a.text).ilike(like),
                func.coalesce(QuestionPair.option_b_text, q_b.short_text, q_b.text).ilike(like),
            )
        )

    total, rows = await _count_and_paginate(
        db,
        QuestionPair,
        filters,
        order_by_clause(
            sort,
            order,
            allowed=QUESTION_PAIR_SORT_FIELDS,
            default=(QuestionPair.instrument.asc(), QuestionPair.pair_index.asc()),
            tiebreaker=QuestionPair.id.asc(),
        ),
        page,
        limit,
        joins=joins,
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


async def clear_question_pair_overrides(
    db: AsyncSession, pair_id: uuid.UUID, field: str | None = None
) -> AdminQuestionPairDetail:
    pair = await _clear_overrides_by_id(
        db, QuestionPair, pair_id, "Question pair not found", field
    )
    return await _build_pair_detail(db, pair)


# --- Motivation statements ---


MOTIVATION_STATEMENT_SORT_FIELDS = {
    "triplet_index": MotivationStatement.triplet_index,
    "order": MotivationStatement.order,
    "category": MotivationStatement.category,
    "text": MotivationStatement.text,
}


async def list_motivation_statements(
    db: AsyncSession,
    *,
    search: str | None = None,
    triplet_index: int | None = None,
    category: MotivationCategory | None = None,
    has_overrides_filter: bool | None = None,
    sort: str | None = None,
    order: SortOrder | None = None,
    page: int = 1,
    limit: int = 20,
) -> AdminMotivationStatementListResponse:
    filters = []
    if search:
        like = f"%{search.strip()}%"
        filters.append(
            or_(MotivationStatement.text.ilike(like), MotivationStatement.text_junior.ilike(like))
        )
    if triplet_index is not None:
        # A triplet is the real unit of meaning here: its three statements must
        # carry three different categories, and nothing server-side enforces
        # that yet, so an admin editing one of them needs to see the other two.
        filters.append(MotivationStatement.triplet_index == triplet_index)
    if category is not None:
        filters.append(MotivationStatement.category == category)
    if has_overrides_filter is not None:
        filters.append(_overrides_filter(MotivationStatement, has_overrides_filter))

    total, rows = await _count_and_paginate(
        db,
        MotivationStatement,
        filters,
        order_by_clause(
            sort,
            order,
            allowed=MOTIVATION_STATEMENT_SORT_FIELDS,
            default=(MotivationStatement.triplet_index.asc(), MotivationStatement.order.asc()),
            tiebreaker=MotivationStatement.id.asc(),
        ),
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


async def _assert_triplet_categories_stay_unique(
    db: AsyncSession, statement: MotivationStatement, updates: dict
) -> None:
    """The three statements of a triplet must carry three different
    categories — the AG(2,3) generator in scripts/motivation_statement_bank.py
    guarantees it for seeded content, but nothing did for an admin edit.

    Until now the check was a line of UI text telling the admin the backend
    would not verify this, on a screen that could not even show the other two
    statements of the triplet. A duplicate silently breaks scoring: the pair
    (MOST, LEAST) stops identifying two distinct motives."""
    new_category = updates.get("category")
    if new_category is None:
        return

    result = await db.execute(
        select(MotivationStatement).where(
            MotivationStatement.triplet_index == statement.triplet_index,
            MotivationStatement.id != statement.id,
            MotivationStatement.category == new_category,
        )
    )
    clash = result.scalars().first()
    if clash is not None:
        raise AdminOverrideValidationError(
            f"Category '{new_category.value}' is already used by statement #{clash.order} "
            f"in triplet {statement.triplet_index} — the three statements of a triplet "
            "must carry three different categories, or scoring cannot tell the picked "
            "motives apart."
        )


async def update_motivation_statement(
    db: AsyncSession, statement_id: uuid.UUID, data: AdminMotivationStatementUpdateRequest
) -> MotivationStatement:
    statement = await _get_by_id(db, MotivationStatement, statement_id)
    if statement is None:
        raise ValueError("Motivation statement not found")

    await _assert_triplet_categories_stay_unique(
        db, statement, data.model_dump(exclude_unset=True)
    )
    return await _update_by_id(
        db, MotivationStatement, statement_id, data, "Motivation statement not found"
    )


async def clear_motivation_statement_overrides(
    db: AsyncSession, statement_id: uuid.UUID, field: str | None = None
) -> MotivationStatement:
    return await _clear_overrides_by_id(
        db, MotivationStatement, statement_id, "Motivation statement not found", field
    )


# --- Motivation pairs ---


MOTIVATION_PAIR_SORT_FIELDS = {
    "pair_index": MotivationPair.pair_index,
    "category_a": MotivationPair.category_a,
}


async def list_motivation_pairs(
    db: AsyncSession,
    *,
    search: str | None = None,
    category: MotivationCategory | None = None,
    has_overrides_filter: bool | None = None,
    sort: str | None = None,
    order: SortOrder | None = None,
    page: int = 1,
    limit: int = 20,
) -> AdminMotivationPairListResponse:
    filters = []
    if search:
        like = f"%{search.strip()}%"
        filters.append(or_(MotivationPair.text_a.ilike(like), MotivationPair.text_b.ilike(like)))
    if category is not None:
        # Both sides of a Harter pair are poles of the SAME category, so one
        # parameter covers the row — matching either column keeps this correct
        # even if that invariant is ever relaxed.
        filters.append(
            or_(MotivationPair.category_a == category, MotivationPair.category_b == category)
        )
    if has_overrides_filter is not None:
        filters.append(_overrides_filter(MotivationPair, has_overrides_filter))

    total, rows = await _count_and_paginate(
        db,
        MotivationPair,
        filters,
        order_by_clause(
            sort,
            order,
            allowed=MOTIVATION_PAIR_SORT_FIELDS,
            default=(MotivationPair.pair_index.asc(),),
            tiebreaker=MotivationPair.id.asc(),
        ),
        page,
        limit,
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


async def clear_motivation_pair_overrides(
    db: AsyncSession, pair_id: uuid.UUID, field: str | None = None
) -> MotivationPair:
    return await _clear_overrides_by_id(
        db, MotivationPair, pair_id, "Motivation pair not found", field
    )


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


DIRECTION_SORT_FIELDS = {
    "name": Direction.name,
    "holland_code": Direction.holland_code,
    "slug": Direction.slug,
}


def _catalog_filled_clause():
    """SQL twin of _empty_catalog_fields() above — kept next to it so the
    filter and the per-row flag can't drift apart. The four list columns
    default to `[]`, never null, so jsonb_array_length is always safe."""
    return and_(
        Direction.description != "",
        *(
            func.jsonb_array_length(getattr(Direction, field)) > 0
            for field in _DIRECTION_CATALOG_FIELDS
            if field != "description"
        ),
    )


async def list_directions(
    db: AsyncSession,
    *,
    search: str | None = None,
    catalog_filled: bool | None = None,
    has_overrides_filter: bool | None = None,
    sort: str | None = None,
    order: SortOrder | None = None,
    page: int = 1,
    limit: int = 20,
) -> AdminDirectionListResponse:
    filters = []
    if search:
        like = f"%{search.strip()}%"
        filters.append(or_(Direction.name.ilike(like), Direction.slug.ilike(like)))
    if catalog_filled is not None:
        clause = _catalog_filled_clause()
        filters.append(clause if catalog_filled else ~clause)
    if has_overrides_filter is not None:
        filters.append(_overrides_filter(Direction, has_overrides_filter))

    total, rows = await _count_and_paginate(
        db,
        Direction,
        filters,
        order_by_clause(
            sort,
            order,
            allowed=DIRECTION_SORT_FIELDS,
            default=(Direction.name.asc(),),
            tiebreaker=Direction.id.asc(),
        ),
        page,
        limit,
    )

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


async def clear_direction_overrides(
    db: AsyncSession, direction_id: uuid.UUID, field: str | None = None
) -> AdminDirectionDetail:
    direction = await _clear_overrides_by_id(
        db, Direction, direction_id, "Direction not found", field
    )
    return await _build_direction_detail(db, direction)
