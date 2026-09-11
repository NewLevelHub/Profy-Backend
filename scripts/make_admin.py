"""
Grant or revoke admin access for an existing Profy user.
Run: docker-compose exec api python scripts/make_admin.py user@example.com
     docker-compose exec api python scripts/make_admin.py user@example.com --revoke
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.user import User, UserRole


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/make_admin.py <email> [--revoke]")
        sys.exit(1)

    email = sys.argv[1].strip().lower()
    grant = "--revoke" not in sys.argv[2:]

    async with async_session() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user:
            print(f"User not found: {email}")
            sys.exit(1)

        if not grant and user.role != UserRole.admin:
            print(f"{email} is not admin (role={user.role.value}) — nothing to revoke.")
            sys.exit(0)

        # `role` replaced the old standalone `is_admin` flag (pro-281) — it's
        # exclusive, so revoking admin always lands on `student`, never on
        # `psychologist`. If this user should become a psychologist instead,
        # use POST /api/v1/admin/users or set role explicitly, not --revoke.
        user.role = UserRole.admin if grant else UserRole.student
        await db.commit()
        print(f"Admin access {'granted to' if grant else 'revoked from'} {email}")


if __name__ == "__main__":
    asyncio.run(main())
