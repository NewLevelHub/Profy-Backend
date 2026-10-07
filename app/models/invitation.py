import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.i18n import KNOWN_LOCALES
from app.models.user import UserRole


class InvitationStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    revoked = "revoked"
    expired = "expired"


class Invitation(Base):
    """Email invitation of a staff member — psychologist or admin (PRO-459).

    No `users` row exists until the invite is accepted (PRO-462): the
    accepting request creates the User with this `role` and `locale`. Kept
    apart from `PasswordResetToken` because the admin UI lists invitations
    with a status and they live much longer than a 15-minute reset code.

    Status is not stored — it is derived from the timestamps (`status_at`),
    so expiry needs no background job. Several rows per `email` are allowed
    (re-invite after expiry/revoke); keeping at most one pending invite per
    email is the service layer's job, since "pending" depends on `now`.

    Only `token_hash` (SHA-256 hex) is stored; the raw token exists only in
    the emailed link.
    """

    __tablename__ = "invitations"
    __table_args__ = (
        CheckConstraint("role <> 'student'", name="ck_invitations_staff_role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum", create_type=False), nullable=False
    )
    # Language of the invitation email; becomes `users.locale` on accept,
    # since the invitee has no user row to read a locale from yet.
    locale: Mapped[str] = mapped_column(
        Enum(*KNOWN_LOCALES, name="locale_enum", create_type=False),
        nullable=False,
        server_default="ru",
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # SET NULL: deleting the inviting admin must not void invites already sent.
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def status_at(self, now: datetime) -> InvitationStatus:
        if self.accepted_at is not None:
            return InvitationStatus.accepted
        if self.revoked_at is not None:
            return InvitationStatus.revoked
        if self.expires_at <= now:
            return InvitationStatus.expired
        return InvitationStatus.pending

    @property
    def status(self) -> InvitationStatus:
        return self.status_at(datetime.now(timezone.utc))
