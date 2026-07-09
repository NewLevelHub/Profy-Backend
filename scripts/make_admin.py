"""
Promote an existing Profy user to admin.
Run: docker-compose exec api python scripts/make_admin.py user@example.com
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.user import User


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/make_admin.py <email>")
        sys.exit(1)

    email = sys.argv[1].strip().lower()

    async with async_session() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user:
            print(f"User not found: {email}")
            sys.exit(1)

        user.is_admin = True
        await db.commit()
        print(f"Admin access granted to {email}")


if __name__ == "__main__":
    asyncio.run(main())
