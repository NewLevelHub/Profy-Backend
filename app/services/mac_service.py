"""МАК — выдача карт и приём ответов (PRO-315). Никакого скоринга: этот
модуль только раздаёт стимулы/карты и сохраняет дословные тексты."""
import random
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.storage.urls import build_public_url
from app.models.mac import MacCard, MacExercise, MacResponse, MacSession
from app.schemas.mac import (
    MacCardOut,
    MacExerciseItem,
    MacSessionResponse,
    SubmitMacResponseRequest,
)


class MacAccessError(ValueError):
    """Сессия/упражнение не найдены или не принадлежат вызывающему — 404."""


def card_to_out(card: MacCard) -> MacCardOut:
    """ORM row -> wire schema. Никогда не отдаём `image_path` (голый
    storage-ключ) клиенту — только готовый абсолютный URL (та же граница,
    что у University.image_url)."""
    return MacCardOut(id=card.id, image_url=build_public_url(card.image_path), kind=card.kind.value)


async def list_active_exercises(db: AsyncSession) -> list[MacExercise]:
    rows = await db.execute(
        select(MacExercise).where(MacExercise.active.is_(True)).order_by(MacExercise.order)
    )
    return list(rows.scalars().all())


async def get_or_create_session(
    db: AsyncSession, *, assessment_id: uuid.UUID, user_id: uuid.UUID
) -> MacSession:
    """Атомарный get-or-create по уникальному `assessment_id` (миграция
    b7e3a5f9c1d4). `ON CONFLICT DO NOTHING` + повторный SELECT — не
    select-then-insert: два параллельных вызова (React StrictMode, повтор
    после сетевой ошибки) больше не могут создать две строки — конфликтующий
    INSERT просто ничего не вставляет, и оба вызова получают одну и ту же
    строку."""
    await db.execute(
        pg_insert(MacSession)
        .values(assessment_id=assessment_id, user_id=user_id)
        .on_conflict_do_nothing(index_elements=["assessment_id"])
    )
    await db.commit()

    session = (
        await db.execute(
            select(MacSession).where(MacSession.assessment_id == assessment_id)
        )
    ).scalar_one()  # freshly selected — no refresh() needed
    return session


async def _responded_exercise_ids(db: AsyncSession, session_id: uuid.UUID) -> set[uuid.UUID]:
    rows = await db.execute(
        select(MacResponse.exercise_id).where(MacResponse.session_id == session_id)
    )
    return {r for (r,) in rows.all()}


async def build_session_response(db: AsyncSession, session: MacSession) -> MacSessionResponse:
    exercises = await list_active_exercises(db)
    responded = await _responded_exercise_ids(db, session.id)
    completed = session.completed_at is not None or (
        bool(exercises) and responded.issuperset(e.id for e in exercises)
    )
    return MacSessionResponse(
        session_id=session.id,
        completed=completed,
        exercises=[MacExerciseItem.model_validate(e) for e in exercises],
    )


async def _require_session(
    db: AsyncSession, session_id: uuid.UUID, *, user_id: uuid.UUID
) -> MacSession:
    session = await db.get(MacSession, session_id)
    if session is None or session.user_id != user_id:
        raise MacAccessError("Session not found")
    return session


async def draw_blind_card(
    db: AsyncSession, *, session_id: uuid.UUID, exercise_id: uuid.UUID, user_id: uuid.UUID
) -> MacCard:
    """Случайная активная карта, ещё не выпадавшая в этой сессии (любое
    упражнение — дедуп на уровне всей сессии, не только текущего)."""
    await _require_session(db, session_id, user_id=user_id)

    used_rows = await db.execute(
        select(MacResponse.card_ids).where(MacResponse.session_id == session_id)
    )
    used: set[str] = set()
    for (ids,) in used_rows.all():
        used.update(str(i) for i in (ids or []))

    cards = (
        await db.execute(select(MacCard).where(MacCard.active.is_(True)))
    ).scalars().all()
    available = [c for c in cards if str(c.id) not in used]
    if not available:
        raise MacAccessError("No cards left in the deck for this session")
    return random.choice(available)


async def get_spread(db: AsyncSession, *, exercise_id: uuid.UUID) -> tuple[list[MacCard], int]:
    exercise = await db.get(MacExercise, exercise_id)
    if exercise is None:
        raise MacAccessError("Exercise not found")
    size = exercise.spread_size or 6
    cards = (
        await db.execute(select(MacCard).where(MacCard.active.is_(True)))
    ).scalars().all()
    spread = random.sample(list(cards), k=min(size, len(cards)))
    return spread, exercise.pick_count


async def submit_response(
    db: AsyncSession, data: SubmitMacResponseRequest, *, user_id: uuid.UUID
) -> tuple[MacResponse, bool]:
    session = await _require_session(db, data.session_id, user_id=user_id)
    exercise = await db.get(MacExercise, data.exercise_id)
    if exercise is None or not exercise.active:
        raise MacAccessError("Exercise not found")

    # `filled_by=parent` (E4, родительский вход) не подключён в этой демке —
    # PRO-316 п.4 ждёт механизм из ресёрча PRO-312. Колонка/схема готовы.
    response = MacResponse(
        session_id=session.id,
        exercise_id=exercise.id,
        subject=data.subject,
        filled_by="client",
        card_ids=[str(i) for i in data.card_ids],
        followup_answers=data.followup_answers,
        time_spent_ms=data.time_spent_ms,
        revision_count=data.revision_count,
    )
    db.add(response)
    await db.flush()

    exercises = await list_active_exercises(db)
    responded = await _responded_exercise_ids(db, session.id)
    responded.add(exercise.id)
    session_completed = bool(exercises) and responded.issuperset(e.id for e in exercises)
    if session_completed and session.completed_at is None:
        from datetime import datetime, timezone
        session.completed_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(response)
    return response, session_completed
