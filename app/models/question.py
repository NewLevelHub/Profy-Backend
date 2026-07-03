import enum
import uuid
from typing import Any

from sqlalchemy import Enum, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.profile import AgeGroup


class QuestionBlock(str, enum.Enum):
    interests = "interests"
    thinking = "thinking"
    personality = "personality"
    motivation = "motivation"
    academic = "academic"
    directions = "directions"
    goal_clarification = "goal_clarification"
    university = "university"
    wellbeing = "wellbeing"


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    block: Mapped[QuestionBlock] = mapped_column(
        Enum(QuestionBlock, name="question_block_enum"), nullable=False, index=True
    )
    age_group: Mapped[AgeGroup] = mapped_column(
        Enum(AgeGroup, name="age_group_enum", create_type=False), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(String, nullable=False)
    options: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
