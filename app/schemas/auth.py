import re
import uuid
from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field, field_validator

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

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        return _validate_password_complexity(v)


class LoginRequest(BaseModel):
    email: NormalizedEmail
    password: str = Field(max_length=PASSWORD_MAX_LENGTH)


class GoogleAuthRequest(BaseModel):
    id_token: str = Field(max_length=GOOGLE_ID_TOKEN_MAX_LENGTH)


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

    model_config = {"from_attributes": True}


class UpdateMeRequest(BaseModel):
    """PATCH /auth/me — currently only the UI locale. Any value in
    `KNOWN_LOCALES` is accepted and stored (a `kk` choice is honored only from
    KZ-603 on); anything else is a 422."""

    locale: str = Field(max_length=LOCALE_MAX_LENGTH)

    @field_validator("locale")
    @classmethod
    def _known_locale(cls, v: str) -> str:
        if v not in KNOWN_LOCALES:
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
