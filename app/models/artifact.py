import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ArtifactType(str, enum.Enum):
    hobby = "hobby"
    club = "club"
    sport = "sport"
    achievement = "achievement"
    goal = "goal"
    book = "book"
    game = "game"
    topic = "topic"
    profession = "profession"
    university = "university"
    dream = "dream"


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id"), nullable=False, index=True
    )
    type: Mapped[ArtifactType] = mapped_column(
        Enum(ArtifactType, name="artifact_type_enum"), nullable=False
    )
    value: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
