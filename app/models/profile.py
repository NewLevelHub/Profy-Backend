import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AgeGroup(str, enum.Enum):
    junior = "junior"
    middle = "middle"
    senior = "senior"


def compute_age_group(age: int) -> AgeGroup:
    if age <= 9:
        return AgeGroup.junior
    if age <= 13:
        return AgeGroup.middle
    return AgeGroup.senior


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    grade: Mapped[int] = mapped_column(Integer, nullable=False)
    city: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str] = mapped_column(String(50), nullable=False)
    subjects_liked: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    subjects_disliked: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    subjects_easy: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    subjects_hard: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    age_group: Mapped[AgeGroup] = mapped_column(
        Enum(AgeGroup, name="age_group_enum"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
