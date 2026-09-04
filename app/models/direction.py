import uuid

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.content_locale_column import locale_column


class Direction(Base):
    __tablename__ = "directions"
    # KZ-301: natural key is slug (shared across locales, never a per-locale
    # slug — see KZ-306); one row per locale. The bare-column UNIQUE this table
    # used to carry is now (slug, locale).
    __table_args__ = (
        UniqueConstraint("slug", "locale", name="uq_directions_slug_locale"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    locale: Mapped[str] = locale_column()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # 3-letter Holland code (e.g. "RIS") — sole basis for career matching
    # (riasec_service.career_match_score). Replaces the old required_scores/
    # bonus_scores threshold scoring entirely.
    holland_code: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
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
    # Field-name -> admin-edited value for name/holland_code, composed on top
    # of the bank content by scripts/seed_riasec_directions.py at resync time
    # (see docs/admin-questions-content-overrides-plan.md). The other fields
    # above are never touched by that script so need no override bookkeeping.
    overrides: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
