import re
import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, EmailStr, Field, field_validator

# Emails are matched case-insensitively everywhere (DB lookups, Google
# account linking) — normalizing once at the request boundary keeps every
# call site consistent instead of relying on each service function to do it.
NormalizedEmail = Annotated[EmailStr, AfterValidator(lambda v: v.strip().lower())]


def _validate_password_complexity(v: str) -> str:
    if not re.search(r"[A-Za-z]", v):
        raise ValueError("Password must contain at least one letter")
    if not re.search(r"\d", v):
        raise ValueError("Password must contain at least one digit")
    return v


class RegisterRequest(BaseModel):
    email: NormalizedEmail
    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        return _validate_password_complexity(v)


class LoginRequest(BaseModel):
    email: NormalizedEmail
    password: str


class GoogleAuthRequest(BaseModel):
    id_token: str


class UserInfo(BaseModel):
    id: uuid.UUID
    email: str
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
    code: str


class ResendVerificationRequest(BaseModel):
    email: NormalizedEmail


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    is_active: bool
    is_verified: bool
    is_admin: bool
    locale: str = "ru"

    model_config = {"from_attributes": True}


class UpdateMeRequest(BaseModel):
    """PATCH /auth/me — currently only the UI locale. `kk` is accepted and
    stored before KZ-603; it just isn't runtime-honored until then."""

    locale: Literal["ru", "kk"]


class ForgotPasswordRequest(BaseModel):
    email: NormalizedEmail


class VerifyResetCodeRequest(BaseModel):
    email: NormalizedEmail
    code: str


class ResetPasswordRequest(BaseModel):
    email: NormalizedEmail
    code: str
    new_password: str = Field(min_length=8)

    @field_validator("new_password")
    @classmethod
    def new_password_complexity(cls, v: str) -> str:
        return _validate_password_complexity(v)
