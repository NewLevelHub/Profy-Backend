import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User

_bearer = HTTPBearer()

# How stale `User.last_active_at` is allowed to get before an authenticated
# request refreshes it. Writing on every request would turn every read
# endpoint into a write and put every active session in contention for its own
# row; the admin screens this feeds ("last seen", "inactive for N days",
# abandoned-diagnostic counts) are all day-scale, so minute-scale precision
# buys nothing.
ACTIVITY_REFRESH_INTERVAL = timedelta(minutes=5)


async def _touch_last_active(db: AsyncSession, user: User) -> None:
    now = datetime.now(timezone.utc)
    last_active = user.last_active_at
    if last_active is not None and now - last_active < ACTIVITY_REFRESH_INTERVAL:
        return

    user.last_active_at = now
    await db.commit()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise credentials_exception

    await _touch_last_active(db, user)
    return user


async def get_current_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user
