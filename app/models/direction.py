import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Direction(Base):
    __tablename__ = "directions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Age groups this direction is offered to. Keeps adult/"heavy" directions
    # (AI, Data Science, …) out of junior/middle results, and keeps the broad
    # kid-friendly "family" directions out of senior results.
    age_groups: Mapped[list] = mapped_column(JSONB, nullable=False, default=lambda: ["senior"])
    required_scores: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    professions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    skills_needed: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    subjects_to_develop: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    first_steps: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Tree taxonomy (Akinator). Old required_scores/bonus_scores scoring keeps
    # running untouched until [GATE] AKN-021 — these columns are additive.
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("directions.id", ondelete="SET NULL"), nullable=True
    )
    # Axis contribution (People, Care, Phys, ... — see app/core/axes.py), −2…+2 per axis.
    profile: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    label_junior: Mapped[str | None] = mapped_column(String(255), nullable=True)
    label_senior: Mapped[str | None] = mapped_column(String(255), nullable=True)
    age_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_leaf: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    parent: Mapped["Direction | None"] = relationship(
        "Direction", remote_side=[id], back_populates="children"
    )
    children: Mapped[list["Direction"]] = relationship(
        "Direction", back_populates="parent"
    )
