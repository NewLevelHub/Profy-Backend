import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DevelopmentPlan(Base):
    """AI «план развития» — единственный сценарий: ученик (senior) выбрал
    профессию и конкретную программу вуза и жмёт «Собрать план развития».

    Всегда привязан к одной программе (`program_id` NOT NULL). Структура
    `stages` вложенная: этап → задача → шаг → микродействие (см.
    app/schemas/development_plan.py). `admission_facts` наполняется бэкендом
    из Program/University и никогда не отдаётся на откуп LLM.
    """

    __tablename__ = "development_plans"
    __table_args__ = (
        UniqueConstraint("assessment_id", "program_id", name="uq_devplan_assessment_program"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    program_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("programs.id", ondelete="CASCADE"),
        nullable=False,
    )
    direction_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    direction_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_foreign: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    target: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    about_you: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    stages: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    skills: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    subjects: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # Backend-populated only (never the LLM's decision): Program/University facts.
    admission_facts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
