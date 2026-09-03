import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, func
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


# GPA was dropped from the product surface (pro-236): the profile API no
# longer accepts or returns `gpa_value`/`gpa_scale`. The columns and this
# enum are kept so the existing `profiles` table (and the `ad95fcc5d772`
# migration already on `dev`) still map cleanly and any values written
# before the removal are preserved, not orphaned — nothing reads them now.
class GpaScale(str, enum.Enum):
    """The grading scale a stored `gpa_value` is expressed on."""

    four = "4"
    five = "5"
    ten = "10"
    hundred = "100"


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
    gpa_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    gpa_scale: Mapped[GpaScale | None] = mapped_column(
        # values_callable: GpaScale member names ("four") don't match their
        # values ("4", the Postgres enum labels) the way every other enum in
        # this app does — without it SQLAlchemy binds `.name` and every
        # write 422s with "invalid input value for enum gpa_scale_enum".
        Enum(GpaScale, name="gpa_scale_enum", values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
