import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserRole(str, enum.Enum):
    """Lightweight role marker added by PRO-291 as a seam only — NOTHING
    enforces access on it yet. `is_admin` stays the source of truth for
    admin checks. PRO-321 («Роль Психолог») is the ticket that turns this
    into a real gate (report_service.psych_sections_for → psychologist/admin
    only); its migration backfills `is_admin=True → role='admin'` so that
    switch is a one-liner. If the team decides against the column before
    then, drop it and leave the TODO anchor in docs/psych-block-contract.md.
    """

    user = "user"
    staff = "staff"
    psychologist = "psychologist"
    admin = "admin"


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
    # Seam for PRO-321 only — not consulted by any access check yet. See UserRole.
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum"),
        nullable=False,
        server_default=UserRole.user.value,
        default=UserRole.user,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
