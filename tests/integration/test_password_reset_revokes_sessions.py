"""Password recovery revokes every access token issued before the reset."""

import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt

from app.config import settings
from app.models.password_reset import PasswordResetToken
from app.models.user import User
from app.services import auth_service
from app.services.token_utils import hash_code


def _authorization(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_successful_password_reset_revokes_current_and_legacy_tokens(
    client,
    db_session,
):
    email = f"{uuid.uuid4()}@example.com"
    old_password = "OldPassword123!"
    new_password = "NewPassword456!"
    code = "123456"
    user = User(
        email=email,
        hashed_password=auth_service.hash_password(old_password),
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    current_token = auth_service.create_jwt_token(user)
    # Tokens created before PROFY-010 have no `ver` claim. They remain valid
    # while the database version is 0, avoiding a mass logout on deployment.
    legacy_token = jwt.encode(
        {
            "sub": str(user.id),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    db_session.add(
        PasswordResetToken(
            user_id=user.id,
            code_hash=hash_code(code),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
    )
    await db_session.commit()

    for token in (current_token, legacy_token):
        response = await client.get("/api/v1/auth/me", headers=_authorization(token))
        assert response.status_code == 200

    reset = await client.post(
        "/api/v1/auth/reset-password",
        json={"email": email, "code": code, "new_password": new_password},
    )
    assert reset.status_code == 200

    await db_session.refresh(user)
    assert user.token_version == 1

    for token in (current_token, legacy_token):
        response = await client.get("/api/v1/auth/me", headers=_authorization(token))
        assert response.status_code == 401

    old_login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": old_password},
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": new_password},
    )
    assert new_login.status_code == 200
    new_token = new_login.json()["access_token"]
    new_claims = jwt.decode(
        new_token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
    )
    assert new_claims["ver"] == 1

    me = await client.get("/api/v1/auth/me", headers=_authorization(new_token))
    assert me.status_code == 200


async def test_failed_password_reset_keeps_existing_session_valid(
    client,
    db_session,
):
    email = f"{uuid.uuid4()}@example.com"
    user = User(
        email=email,
        hashed_password=auth_service.hash_password("OldPassword123!"),
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    token = auth_service.create_jwt_token(user)
    db_session.add(
        PasswordResetToken(
            user_id=user.id,
            code_hash=hash_code("123456"),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
    )
    await db_session.commit()

    reset = await client.post(
        "/api/v1/auth/reset-password",
        json={
            "email": email,
            "code": "654321",
            "new_password": "NewPassword456!",
        },
    )
    assert reset.status_code == 400

    await db_session.refresh(user)
    assert user.token_version == 0
    me = await client.get("/api/v1/auth/me", headers=_authorization(token))
    assert me.status_code == 200
