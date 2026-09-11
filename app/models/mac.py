"""МАК — метафорические ассоциативные карты (PRO-314). Схема §8
`тестМак.md`. Никакого скоринга: карты/упражнения — конфиг, прохождение —
стимул → карта(ы) → дословный текст ребёнка. `MacNote`/`MacSummary` — рабочее
поле специалиста (только staff-экран, PRO-318 workspace); в `/result`
школьнику не отдаются.

v1 (сегодняшняя демка, PRO-312/313 ресёрч ещё не закрыт): активно только
упражнение E1 (`blind`, 1 карта); E2–E6 заведены в конфиге как `active=False`
заготовки — раскладка (`open`), режим родителя (E4) и текстовая колода (E6)
подключаются, когда придёт финальный список от психолога.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Enum, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MacCardKind(str, enum.Enum):
    abstract = "abstract"
    scenic = "scenic"
    portrait = "portrait"


class MacDrawMode(str, enum.Enum):
    blind = "blind"  # система выдаёт случайную карту
    open = "open"  # раскладка face-up, ребёнок выбирает сам


class MacFilledBy(str, enum.Enum):
    client = "client"
    parent = "parent"  # E4


class MacCard(Base):
    """Колода. `image_path` — относительный путь статики на фронте
    (`/mac-cards/<file>`), бэкенд байты не хранит и не отдаёт."""

    __tablename__ = "mac_cards"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    image_path: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    kind: Mapped[MacCardKind] = mapped_column(
        Enum(MacCardKind, name="mac_card_kind_enum"), nullable=False
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=func.true())
    # PRO-311 (лицензия финальной колоды) не закрыт — для демо-колоды null.
    license: Mapped[str | None] = mapped_column(String(120), nullable=True)
    attribution: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MacExercise(Base):
    """Конфиг упражнения (E1…E6), меняется редко — правится сидом, не в БД
    руками (тот же контракт, что question-банки)."""

    __tablename__ = "mac_exercises"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(String(8), nullable=False, unique=True)  # E1..E6
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    stimulus_question: Mapped[str] = mapped_column(String(500), nullable=False)
    draw_mode: Mapped[MacDrawMode] = mapped_column(
        Enum(MacDrawMode, name="mac_draw_mode_enum"), nullable=False
    )
    spread_size: Mapped[int | None] = mapped_column(Integer, nullable=True)  # open only
    pick_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    followup_questions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    subjects: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # E4: self/parents/teachers/friends
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=func.false())


class MacSession(Base):
    """Одно прохождение блока МАК (append-only историю не ведём — по одному
    прохождению на assessment достаточно для v1). `assessment_id` UNIQUE —
    не только по замыслу, но и физически в БД (миграция b7e3a5f9c1d4):
    `mac_service.get_or_create_session` полагается на `ON CONFLICT DO
    NOTHING` по этому ограничению, чтобы гонка двух параллельных запросов
    (например, React StrictMode дважды монтирует эффект в dev) не плодила
    дублирующие сессии — второй ответ отчёта иначе падает с
    `MultipleResultsFound`, молча гасится try/except изоляции психоблока, и
    психолог просто не видит секцию."""

    __tablename__ = "mac_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    consent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consents.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MacResponse(Base):
    """Один ответ на упражнение внутри сессии: стимул из `mac_exercises`,
    карта(ы), дословные тексты наводящих вопросов. Никакой телеметрии сверх
    `time_spent_ms`/`revision_count`."""

    __tablename__ = "mac_responses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mac_sessions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    exercise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mac_exercises.id", ondelete="RESTRICT"), nullable=False
    )
    subject: Mapped[str | None] = mapped_column(String(32), nullable=True)  # E4 only
    filled_by: Mapped[MacFilledBy] = mapped_column(
        Enum(MacFilledBy, name="mac_filled_by_enum"), nullable=False,
        server_default=MacFilledBy.client.value,
    )
    card_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    followup_answers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    time_spent_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    revision_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MacNote(Base):
    """Рабочее поле специалиста — подсветка фразы + тег-гипотеза. Только
    staff-экран (PRO-318 workspace, НЕ реализован в этой демке); модель
    заведена, чтобы схема §8 была покрыта полностью."""

    __tablename__ = "mac_notes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mac_sessions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    response_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mac_responses.id", ondelete="CASCADE"), nullable=True
    )
    text: Mapped[str] = mapped_column(String(2000), nullable=False)
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MacSummary(Base):
    """Итоговое резюме специалиста по сессии. Только staff-экран (не
    реализован в этой демке); модель заведена по той же причине, что MacNote."""

    __tablename__ = "mac_summaries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mac_sessions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    text: Mapped[str] = mapped_column(String(4000), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
