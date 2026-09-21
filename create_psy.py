import asyncio
from app.database import async_session
from app.models.user import User, UserRole
from app.services.auth_service import hash_password

async def main():
    async with async_session() as db:
        user = User(
            email='psy@profor.me',
            hashed_password=hash_password('04091998A'),
            role=UserRole.psychologist,
            is_verified=True
        )
        db.add(user)
        await db.commit()
        print('User created successfully')

asyncio.run(main())
