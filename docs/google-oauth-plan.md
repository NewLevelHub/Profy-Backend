# Google OAuth login — implementation plan

## Context

Product wants a "Sign in with Google" option in addition to the existing
email/password flow. Nothing OAuth-related exists in the codebase yet
(`grep -ri "oauth\|google"` across `.py`/`.md`/`.yml` returns nothing
auth-related) — this is a from-scratch design, not a fix to something
partially built.

Relevant current state:

- Auth is entirely email/password, stateless Bearer-JWT
  (`app/routers/auth.py`, `app/services/auth_service.py`,
  `app/dependencies.py`). `create_jwt_token` (`auth_service.py:30-33`) signs
  a flat `{"sub": user_id, "exp": ...}` payload with `settings.SECRET_KEY`/
  `settings.ALGORITHM`; tokens are valid for `ACCESS_TOKEN_EXPIRE_MINUTES`
  (24h) with **no refresh-token mechanism** at all today.
- `User` (`app/models/user.py`): `hashed_password` is `String(255),
  nullable=False`; no provider/external-id columns; `email` has a unique
  index.
- `get_current_user` (`app/dependencies.py:16-44`) decodes the Bearer JWT
  and loads the user — this doesn't need to change, since OAuth login will
  ultimately issue the same JWT shape via the same `create_jwt_token`.
- CORS is wide open (`app/main.py:30-36`, `allow_origins=["*"]`) and there is
  **no session/cookie middleware anywhere** — everything is Bearer-token
  based, no redirect/callback infrastructure exists.
- `httpx==0.28.1` is already a dependency; no `google-auth`/`authlib` yet.
- Two clients consume this API: the mobile app (Profi, this repo's primary
  client per `README.md`) and a separate web frontend (`Profy-Frontend`,
  sibling repo, not present locally, referenced from `nginx/local.conf` and
  `docs/nginx-prod-points-to-dev-incident.md`).
- Settings (`app/config.py`) use bare-uppercase names with no shared prefix
  beyond the service name (`SECRET_KEY`, `ALGORITHM`, `RESEND_API_KEY`,
  `LLM_API_KEY`, ...) — a new Google setting should follow the same
  convention (`GOOGLE_CLIENT_ID`, not `JWT_GOOGLE...` or similar).
- This repo has 60+ Alembic migrations with **multiple parallel heads**
  (per CLAUDE.md) — `alembic heads` must be run at implementation time to
  find the real `down_revision`, not inferred from filenames.

## Design (confirmed with user)

- **ID-token verification flow, not a server-side redirect/authorization-code
  flow.** The web frontend performs Google Identity Services sign-in
  client-side (the standard "Sign in with Google" JS button/One Tap) and
  gets back a Google-issued ID token (a signed JWT). It POSTs that token to
  a new backend endpoint. The backend verifies the token's signature,
  audience, and expiry against Google's public keys and, on success, issues
  the app's own existing JWT via `create_jwt_token`. This fits the current
  stateless Bearer-JWT design exactly — no cookies, no server-side session,
  no `redirect_uri`/callback route, no CSRF `state` param to manage. It also
  works identically for a future mobile client (same shape, different
  `id_token` source) without needing separate infrastructure.
- **Auto-link by email.** If a Google ID token's verified email matches an
  existing password-registered account, the backend attaches `google_id` to
  that existing row instead of creating a duplicate user or rejecting the
  login. Google has already verified ownership of that email address, so
  this is safe and is standard practice (GitHub, Slack, etc. all do this).
- **Scope for this pass: web frontend only.** A single `GOOGLE_CLIENT_ID`
  (one audience) is enough. Mobile (Profi) Google Sign-In is deferred — see
  Not in scope for the (small) follow-up this implies.

## Changes

### 1. New setting — `app/config.py` / `.env.example`

```python
# app/config.py, alongside the other bare-uppercase settings
GOOGLE_CLIENT_ID: str = ""
```

```bash
# .env.example, new block after the "Email / Resend" block
# Google OAuth (web sign-in) — from Google Cloud Console > APIs & Services >
# Credentials > OAuth 2.0 Client IDs > Web application. Add the frontend's
# origin(s) as an "Authorized JavaScript origin" there.
GOOGLE_CLIENT_ID=
```

### 2. New dependency — `requirements.txt`

Add `google-auth` (pin the exact version at implementation time, matching
this repo's convention of pinning every dependency, e.g. `resend==2.39.0`).
Provides `google.oauth2.id_token.verify_oauth2_token`, which validates the
token's signature against Google's JWKS (cached/refreshed internally) and
checks `iss`/`exp`.

### 3. New Alembic migration

Resolve the real current head with `alembic heads` at implementation time
(do not assume the last-modified file in `alembic/versions/` is it — this
repo has multiple parallel branches). The migration:

```python
def upgrade() -> None:
    op.alter_column("users", "hashed_password", nullable=True)
    op.add_column("users", sa.Column("google_id", sa.String(255), nullable=True))
    op.create_unique_constraint("uq_users_google_id", "users", ["google_id"])
    op.create_index("ix_users_google_id", "users", ["google_id"])
```

`hashed_password` must become nullable because a Google-only signup never
sets a password.

### 4. `app/models/user.py`

```python
hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
google_id: Mapped[str | None] = mapped_column(
    String(255), unique=True, nullable=True, index=True
)
```

### 5. `app/schemas/auth.py`

```python
class GoogleAuthRequest(BaseModel):
    id_token: str
```

The response reuses the existing `TokenResponse` (`access_token`,
`token_type`, `user: UserInfo`) — no new response schema needed.

### 6. New `app/services/oauth_service.py`

Plain module-level functions, mirroring `auth_service.py`'s style (not a
class) and its exception-based control-flow convention (`ValueError` /
`LookupError` raised from the service, mapped to HTTP codes in the router):

```python
import asyncio

from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.services.auth_service import create_jwt_token

_google_request = google_requests.Request()


async def verify_google_id_token(token: str) -> dict:
    try:
        claims = await asyncio.to_thread(
            google_id_token.verify_oauth2_token,
            token,
            _google_request,
            settings.GOOGLE_CLIENT_ID,
        )
    except ValueError as exc:
        raise ValueError("Invalid Google token") from exc

    if not claims.get("email_verified"):
        raise ValueError("Google email not verified")

    return claims


async def login_or_register_google(token: str, db: AsyncSession) -> tuple[User, str]:
    claims = await verify_google_id_token(token)
    google_id, email = claims["sub"], claims["email"]

    result = await db.execute(select(User).where(User.google_id == google_id))
    user = result.scalar_one_or_none()

    if not user:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user:
            user.google_id = google_id
            user.is_verified = True
        else:
            user = User(
                email=email,
                hashed_password=None,
                google_id=google_id,
                is_verified=True,
            )
            db.add(user)
        await db.commit()
        await db.refresh(user)

    return user, create_jwt_token(user.id)
```

(`asyncio.to_thread` wraps the blocking Google HTTP/verification call, the
same pattern already used for the `resend` SDK call in
`app/services/email_service.py:42`.)

### 7. `app/routers/auth.py`

```python
@router.post("/google", response_model=TokenResponse)
async def google_login(body: GoogleAuthRequest, db: AsyncSession = Depends(get_db)):
    try:
        user, token = await oauth_service.login_or_register_google(body.id_token, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return TokenResponse(access_token=token, user=user)
```

Same shape as `/register`'s `except ValueError` handling (`auth.py:60-61`).

### 8. `app/services/auth_service.py::login()`

Guard the now-nullable `hashed_password`:

```python
async def login(email: str, password: str, db: AsyncSession) -> tuple[User, str]:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password or not verify_password(password, user.hashed_password):
        raise PermissionError("Invalid credentials")

    if user.hashed_password is None:
        raise LookupError(f"google_account:{user.email}")

    if not user.is_verified:
        raise LookupError(f"email_not_verified:{user.email}")

    return user, create_jwt_token(user.id)
```

(Order matters: the `hashed_password is None` check must come before the
`verify_password` call it would otherwise crash — written above as a
short-circuited boolean rather than two separate checks; adjust to taste.)

In the router, handle this alongside the existing `email_not_verified`
branch (`auth.py:70-75`):

```python
except LookupError as exc:
    kind, value = str(exc).split(":", 1)
    if kind == "google_account":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"detail": "google_account", "email": value},
        )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"detail": "email_not_verified", "email": value},
    )
```

This lets the frontend show "this account uses Google — continue with
Google" instead of a generic invalid-credentials error.

### 9. `password_reset_service.py` — no code changes needed

`reset_password` (`password_reset_service.py:101`) already unconditionally
does `user.hashed_password = hash_password(new_password)` with no
null-check beforehand. Once `hashed_password` is nullable, a Google-only
user who goes through "forgot password" will naturally end up with a
password set — i.e. they gain password-login as a side effect, for free.
This is flagged here deliberately so it's a known, accepted consequence
rather than something discovered by surprise later.

## Not in scope

- **Mobile app (Profi) Google Sign-In.** Needs separate Android/iOS OAuth
  client IDs from Google Cloud Console. The extension is small: widen
  `GOOGLE_CLIENT_ID: str` to `GOOGLE_CLIENT_IDS: str` (comma-separated),
  parse into a list, and pass that list as the `audience` argument to
  `verify_oauth2_token` (it accepts an iterable of acceptable audiences).
  No other part of this design changes.
- **Account unlinking** ("remove Google" / revert to password-only).
- **A dedicated "set password" endpoint** for Google-only accounts — the
  existing forgot-password flow already covers this (see Changes #9).
- **Refresh tokens** — consistent with the rest of the auth system today,
  which has none.
- **Redis rate-limiting on `/auth/google`** — the token is Google-signed and
  not guessable by brute force the way a password or a 6-digit code is, so
  the rate-limiting applied to the other auth endpoints
  (`_check_rate_limit`, `auth.py:44-53`) isn't meaningful here. Basic IP
  throttling could be added later if abuse is observed.

## Verification

1. Create a Web OAuth 2.0 Client ID in Google Cloud Console, add the
   frontend's origin as an authorized JavaScript origin, set
   `GOOGLE_CLIENT_ID` in `.env`.
2. Run the new migration locally (`alembic upgrade head`); confirm
   `users.hashed_password` is nullable and `users.google_id` exists
   (unique, nullable, indexed).
3. From the frontend (or a manual Google Identity Services test page), sign
   in with a Google account whose email is not yet in the DB. Confirm
   `POST /api/v1/auth/google` returns a `TokenResponse`, and the created row
   has `hashed_password IS NULL`, `google_id` set, `is_verified = true`.
4. Repeat with an email that already has a password account — confirm the
   *existing* row gets `google_id` populated (no duplicate user created),
   and `GET /me` with the returned token resolves to the same user id as
   before.
5. `POST /auth/login` with that Google-only account's email + any password
   — confirm `403` with `{"detail": "google_account", ...}`, not a generic
   `401`.
6. `POST /auth/google` with a tampered or expired `id_token` — confirm
   `400`.
7. `POST /auth/forgot-password` → `verify-reset-code` → `reset-password` for
   a Google-only account — confirm it succeeds and the account can now also
   log in with the new password (the item #9 side effect).
8. `docker compose exec api pytest tests/unit` — add unit tests for
   `oauth_service` (mock `verify_google_id_token`) covering: new-user
   creation, existing-password-account linking, existing-Google-user
   relogin, and the `login()` 403 guard for Google-only accounts. This
   change introduces no new module-level Redis singleton, so no
   `_REDIS_SINGLETON_MODULES` update is needed in `tests/conftest.py`.
