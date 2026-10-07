"""Staff invitations (PRO-457). Contract:
docs/frontend-admin-invitations-api-contract.md."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.i18n import DEFAULT_LOCALE, KNOWN_LOCALES
from app.i18n.catalog import key as i18n_key
from app.models.invitation import InvitationStatus
from app.models.user import UserRole
from app.schemas.auth import NormalizedEmail, _validate_password_complexity


class AdminInvitationCreate(BaseModel):
    email: NormalizedEmail
    role: UserRole
    # Language of the email; becomes `users.locale` on accept.
    locale: str = DEFAULT_LOCALE

    @field_validator("role")
    @classmethod
    def role_not_student(cls, v: UserRole) -> UserRole:
        if v == UserRole.student:
            raise ValueError(i18n_key("api_errors", "student_registration_required"))
        return v

    @field_validator("locale")
    @classmethod
    def known_locale(cls, v: str) -> str:
        if v not in KNOWN_LOCALES:
            raise ValueError(
                i18n_key("api_errors", "unsupported_locale").format(locales=sorted(KNOWN_LOCALES))
            )
        return v


class InvitationInviter(BaseModel):
    id: uuid.UUID
    email: str


class AdminInvitationItem(BaseModel):
    id: uuid.UUID
    email: str
    role: UserRole
    locale: str
    status: InvitationStatus
    # null once the inviting admin is deleted (FK is SET NULL).
    invited_by: InvitationInviter | None
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None


class AdminInvitationSent(AdminInvitationItem):
    """create / resend: the raw link exists only here — the DB keeps a hash."""

    invite_url: str
    # False when the provider failed; the invitation is still valid and the
    # admin hands `invite_url` over manually.
    email_sent: bool


class AdminInvitationListResponse(BaseModel):
    items: list[AdminInvitationItem]
    total: int
    page: int
    limit: int


class InvitationPreview(BaseModel):
    """GET /auth/invitations/{token} — what the /invite page shows."""

    email: str
    role: UserRole
    locale: str
    expires_at: datetime


class AcceptInvitationRequest(BaseModel):
    token: str
    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        return _validate_password_complexity(v)
