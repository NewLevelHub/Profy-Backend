import uuid

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Direction(Base):
    __tablename__ = "directions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    # 3-letter Holland code (e.g. "RIS") — sole basis for career matching
    # (riasec_service.career_match_score). Replaces the old required_scores/
    # bonus_scores threshold scoring entirely.
    holland_code: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    # One or more of the ~10 curated categories also used for
    # Program.direction_slug (see scripts/specialty_category_lookup.py) —
    # bridges the profession catalog to the university/program tagging
    # vocabulary, which uses a much coarser taxonomy than individual
    # profession slugs. A list because some professions (e.g. "Архитектор")
    # genuinely span more than one category's real programs.
    category_slugs: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # Descriptive fields kept for downstream consumers (report_service,
    # roadmap_builder, direction_inquiry_service, frontend DirectionDetailPage)
    # that predate this migration. The new profession catalog (seeded from
    # scripts/riasec_professions.py) only has name+code, so these are empty
    # by default until a future content pass fills them in — see
    # TICKET-riasec-migration.md / plan Context for the accepted trade-off.
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    professions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    skills_needed: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    subjects_to_develop: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    first_steps: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
