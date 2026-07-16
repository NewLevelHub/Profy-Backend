import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProfessionSimulation(Base):
    """Realistic Job Preview: roleplay mini-test content for leaf professions.

    Includes the text of situations (specifically non-glamorous ones) and options.
    """

    __tablename__ = "profession_simulations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    leaf_slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    # A list of dictionaries representing scenario steps
    steps: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
