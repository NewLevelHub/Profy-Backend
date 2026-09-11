"""
Create or update an admin user with given credentials.
Run inside the api container:
  docker compose exec api python scripts/create_admin_user.py <email> <password>
"""
import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select

from app.database import async_session
from app.models.user import User, UserRole
from app.services.auth_service import hash_password


async def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python scripts/create_admin_user.py <email> <password>")
        sys.exit(1)

    email = sys.argv[1].strip().lower()
    password = sys.argv[2].strip()

    async with async_session() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user:
            print(f"User {email} already exists. Updating to admin and resetting password...")
            user.hashed_password = hash_password(password)
            user.role = UserRole.admin
            user.is_active = True
            user.is_verified = True
        else:
            print(f"Creating new admin user: {email}...")
            user = User(
                email=email,
                hashed_password=hash_password(password),
                is_active=True,
                is_verified=True,
                role=UserRole.admin,
            )
            db.add(user)

        await db.commit()
        print(f"Admin user {email} is ready.")


if __name__ == "__main__":
    asyncio.run(main())
