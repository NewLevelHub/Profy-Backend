import re
import uuid
from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field, StringConstraints, field_validator

from app.i18n.catalog import key as i18n_key
from app.i18n import KNOWN_LOCALES
from app.models.user import UserRole
from app.schemas.validation import LOCALE_MAX_LENGTH

# Emails are matched case-insensitively everywhere (DB lookups, Google
# account linking) — normalizing once at the request boundary keeps every
# call site consistent instead of relying on each service function to do it.
NormalizedEmail = Annotated[EmailStr, AfterValidator(lambda v: v.strip().lower())]

# Long enough for any passphrase; the cap keeps a megabyte "password" from
# being fed to the password hash, which is slow on purpose.
PASSWORD_MAX_LENGTH = 128
# The emailed code is six digits; anything much longer is not a guess at it.
CODE_MAX_LENGTH = 16
# A Google ID token is a JWT of about 1–2 KB.
GOOGLE_ID_TOKEN_MAX_LENGTH = 8192


def _validate_password_complexity(v: str) -> str:
    if not re.search(r"[A-Za-z]", v):
        raise ValueError(i18n_key("api_errors", "password_letter_required"))
    if not re.search(r"\d", v):
        raise ValueError(i18n_key("api_errors", "password_digit_required"))
    return v


class RegisterRequest(BaseModel):
    email: NormalizedEmail
    password: str = Field(min_length=8, max_length=PASSWORD_MAX_LENGTH)
    # The CRM invite token (ТЗ §4.4): required while registration is invite-only.
    student_invite: str | None = Field(default=None, max_length=128)

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        return _validate_password_complexity(v)


class LoginRequest(BaseModel):
    email: NormalizedEmail
    password: str = Field(max_length=PASSWORD_MAX_LENGTH)


class GoogleAuthRequest(BaseModel):
    id_token: str = Field(max_length=GOOGLE_ID_TOKEN_MAX_LENGTH)
    # Needed only when the Google account has no Profile account yet.
    student_invite: str | None = Field(default=None, max_length=128)


class UserInfo(BaseModel):
    id: uuid.UUID
    email: str
    role: UserRole = UserRole.student
    is_admin: bool = False
    locale: str = "ru"

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo


class RegisterResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    message: str


class VerifyEmailRequest(BaseModel):
    email: NormalizedEmail
    code: str = Field(max_length=CODE_MAX_LENGTH)


class ResendVerificationRequest(BaseModel):
    email: NormalizedEmail


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    is_active: bool
    is_verified: bool
    role: UserRole
    is_admin: bool
    locale: str = "ru"
    # Staff name (CRM sidebar, PRO-497); students have none.
    full_name: str | None = None

    model_config = {"from_attributes": True}


class UpdateMeRequest(BaseModel):
    """PATCH /auth/me — the UI locale and a staff member's name; each is
    optional and left alone when not sent. Any locale in `KNOWN_LOCALES` is
    accepted and stored (a `kk` choice is honored only from KZ-603 on);
    anything else is a 422. The name is staff-only: an invited specialist
    whose invitation had none sets it on the first sign-in."""

    locale: str | None = Field(default=None, max_length=LOCALE_MAX_LENGTH)
    full_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=255)] | None = None

    @field_validator("locale")
    @classmethod
    def _known_locale(cls, v: str | None) -> str | None:
        if v is not None and v not in KNOWN_LOCALES:
            raise ValueError(i18n_key("api_errors", "unsupported_locale").format(locales=sorted(KNOWN_LOCALES)))
        return v


class ForgotPasswordRequest(BaseModel):
    email: NormalizedEmail


class VerifyResetCodeRequest(BaseModel):
    email: NormalizedEmail
    code: str = Field(max_length=CODE_MAX_LENGTH)


class ResetPasswordRequest(BaseModel):
    email: NormalizedEmail
    code: str = Field(max_length=CODE_MAX_LENGTH)
    new_password: str = Field(min_length=8, max_length=PASSWORD_MAX_LENGTH)

    @field_validator("new_password")
    @classmethod
    def new_password_complexity(cls, v: str) -> str:
        return _validate_password_complexity(v)
