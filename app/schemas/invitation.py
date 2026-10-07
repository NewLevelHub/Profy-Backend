"""Staff invitations (PRO-457). Contract:
docs/frontend-admin-invitations-api-contract.md.

Validation failures raise `PydanticCustomError` with catalog text (see
`app/schemas/validation.py`), so a 422 reads in the request locale instead
of pydantic's built-in English.
"""

import re
import uuid
from datetime import datetime
from typing import Any

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, field_validator
from pydantic_core import PydanticCustomError

from app.i18n import DEFAULT_LOCALE, KNOWN_LOCALES
from app.i18n.catalog import key as i18n_key
from app.models.invitation import InvitationStatus
from app.models.user import UserRole

_STAFF_ROLES = (UserRole.psychologist.value, UserRole.admin.value)
_PASSWORD_MIN_LENGTH = 8


def _invalid(error_code: str, **params: Any) -> PydanticCustomError:
    return PydanticCustomError(error_code, i18n_key("api_errors", error_code).format(**params))


class AdminInvitationCreate(BaseModel):
    email: str
    role: UserRole
    # Language of the email; becomes `users.locale` on accept.
    locale: str = DEFAULT_LOCALE

    @field_validator("email", mode="before")
    @classmethod
    def valid_email(cls, v: Any) -> str:
        # Same check as `EmailStr` (no DNS), normalized like `NormalizedEmail`.
        try:
            return validate_email(str(v).strip(), check_deliverability=False).normalized.lower()
        except EmailNotValidError:
            raise _invalid("invitation_email_invalid") from None

    @field_validator("role", mode="before")
    @classmethod
    def staff_role(cls, v: Any) -> Any:
        # Students register themselves; only staff are invited.
        if getattr(v, "value", v) not in _STAFF_ROLES:
            raise _invalid("invitation_role_invalid")
        return v

    @field_validator("locale", mode="before")
    @classmethod
    def known_locale(cls, v: Any) -> Any:
        if v not in KNOWN_LOCALES:
            raise _invalid("invitation_locale_invalid", locales=", ".join(KNOWN_LOCALES))
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
    password: str

    @field_validator("password")
    @classmethod
    def password_rules(cls, v: str) -> str:
        # The registration rule (`_validate_password_complexity`), localized.
        if len(v) < _PASSWORD_MIN_LENGTH:
            raise _invalid("password_too_short", min_length=_PASSWORD_MIN_LENGTH)
        if not re.search(r"[A-Za-z]", v):
            raise _invalid("password_letter_required")
        if not re.search(r"\d", v):
            raise _invalid("password_digit_required")
        return v
