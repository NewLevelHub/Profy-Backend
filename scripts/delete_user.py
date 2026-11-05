"""
Permanently delete a Profy user and all their data.
Run: docker-compose exec api python scripts/delete_user.py user@example.com

Deletes the account the way `app/services/user_deletion.py` does, without its
checks and without a journal entry: this is also how an owner or an admin goes.
All in one transaction: either everything goes, or nothing does.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.user import User
from app.services import user_deletion


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/delete_user.py <email>")
        sys.exit(1)

    email = sys.argv[1].strip().lower()

    async with async_session() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user:
            print(f"User not found: {email}")
            sys.exit(1)

        await user_deletion.purge(db, user)
        await db.commit()
        print(f"Deleted {email}")


if __name__ == "__main__":
    asyncio.run(main())
