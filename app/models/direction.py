import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Column names whose value is a `{"ru": ..., "kk": ...}` (or `{"ru": [...],
# "kk": [...]}`) map rather than a plain scalar — one row per direction now
# (see docs/i18n-contract.md §8; this replaced the former one-row-per-locale
# "variant A" design), read via app.i18n.pick_locale/pick_locale_list and
# used by admin_lock.apply_overrides/sync_fields to know which fields need
# per-locale merge semantics instead of a flat overwrite.
LOCALIZED_FIELDS = frozenset(
    {"name", "description", "professions", "skills_needed", "subjects_to_develop", "first_steps"}
)


class Direction(Base):
    __tablename__ = "directions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Natural key, locale-invariant (see KZ-306) — computed from the `ru`
    # title, never translated itself, so this stays a plain unique column.
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    # 3-letter Holland code (e.g. "RIS") — still used for display, meta
    # (consistency / development_plan), and as a fallback career-match score
    # when `onet_vector` is missing. Not localized.
    holland_code: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    # Full 6-dim O*NET RIASEC interest vector {"R": .., "I": .., ...} used by
    # Pearson career matching (PRO-385). NULL for the few catalog entries
    # without a US SOC analogue — those fall back to holland_code scoring.
    onet_vector: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)
    # Descriptive fields kept for downstream consumers (report_service,
    # frontend DirectionDetailPage)
    # that predate this migration. The new profession catalog (seeded from
    # scripts/riasec_professions.py) only has name+code, so these are empty
    # by default until a future content pass fills them in — see
    # TICKET-riasec-migration.md / plan Context for the accepted trade-off.
    description: Mapped[dict] = mapped_column(JSONB, nullable=False, default=lambda: {"ru": ""})
    professions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=lambda: {"ru": []})
    skills_needed: Mapped[dict] = mapped_column(JSONB, nullable=False, default=lambda: {"ru": []})
    subjects_to_develop: Mapped[dict] = mapped_column(JSONB, nullable=False, default=lambda: {"ru": []})
    first_steps: Mapped[dict] = mapped_column(JSONB, nullable=False, default=lambda: {"ru": []})
    # Field-name -> admin-edited value for name/holland_code, composed on top
    # of the bank content by scripts/seed_riasec_directions.py at resync time
    # (see docs/admin-questions-content-overrides-plan.md). The other fields
    # above are never touched by that script so need no override bookkeeping.
    overrides: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
