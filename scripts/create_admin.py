"""
Create (or upgrade) a verified admin user directly, bypassing email verification.
Run: docker-compose exec api python scripts/create_admin.py <email> <password>
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.user import User
from app.services.auth_service import hash_password


async def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python scripts/create_admin.py <email> <password>")
        sys.exit(1)

    email = sys.argv[1].strip().lower()
    password = sys.argv[2]

    async with async_session() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user:
            user.hashed_password = hash_password(password)
            user.is_verified = True
            user.is_admin = True
            await db.commit()
            print(f"Updated existing user to admin: {email}")
            return

        user = User(
            email=email,
            hashed_password=hash_password(password),
            is_verified=True,
            is_admin=True,
        )
        db.add(user)
        await db.commit()
        print(f"Created admin user: {email}")


if __name__ == "__main__":
    asyncio.run(main())
