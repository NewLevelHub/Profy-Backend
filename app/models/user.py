import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, false, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.i18n import KNOWN_LOCALES


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # UI locale ("ru" | "kk"). Plain-string Enum (values, not a Python enum
    # class) so `user.locale` is a str, not `Locale.ru`. Distinct from
    # `profiles.language` (language of instruction). See docs/i18n-contract.md.
    # "kk" is stored but not runtime-honored until KZ-603 (no feature flag).
    # Enum values come from KNOWN_LOCALES so this and the persistence contract
    # can't drift; the `locale_enum` Postgres type is still owned by Alembic
    # (migration d80fbf5d1f43) — see the KNOWN_LOCALES comment in app/i18n.py
    # before adding a value.
    locale: Mapped[str] = mapped_column(
        Enum(*KNOWN_LOCALES, name="locale_enum", create_type=False),
        nullable=False,
        server_default="ru",
    )
    # Set once the user picks a locale via the switcher. While False, creating a
    # profile may pre-fill `locale` from `profiles.language`; once True that
    # pre-fill is permanently skipped (docs/i18n-contract.md §6).
    locale_explicit: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
