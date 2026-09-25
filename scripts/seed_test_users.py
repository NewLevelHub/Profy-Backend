"""
Seed test users with profiles for local development.
Run inside the api container:
  docker compose exec api python scripts/seed_test_users.py
"""
import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select

from app.database import async_session
from app.models.profile import AgeGroup, Profile, compute_age_group
from app.models.user import User, UserRole
from app.services.auth_service import hash_password

TEST_USERS = [
    {
        "email": "student_senior@test.com",
        "password": "test1234",
        "role": UserRole.student,
        "locale": "ru",
        "profile": {
            "name": "Азат Сейткали",
            "age": 16,
            "grade": 10,
            "city": "Алматы",
            "country": "Казахстан",
            "language": "ru",
            "subjects_liked": ["Биология", "Химия"],
            "subjects_disliked": ["Физкультура"],
            "subjects_easy": ["Биология", "История"],
            "subjects_hard": ["Физика"],
        },
    },
    {
        "email": "student_middle@test.com",
        "password": "test1234",
        "role": UserRole.student,
        "locale": "ru",
        "profile": {
            "name": "Дана Нурланова",
            "age": 13,
            "grade": 7,
            "city": "Астана",
            "country": "Казахстан",
            "language": "ru",
            "subjects_liked": ["Математика", "Информатика"],
            "subjects_disliked": ["Литература"],
            "subjects_easy": ["Математика"],
            "subjects_hard": ["Казахский язык"],
        },
    },
    {
        "email": "student_junior@test.com",
        "password": "test1234",
        "role": UserRole.student,
        "locale": "kk",
        "profile": {
            "name": "Арман Беков",
            "age": 9,
            "grade": 3,
            "city": "Шымкент",
            "country": "Казахстан",
            "language": "kk",
            "subjects_liked": ["Рисование", "Музыка"],
            "subjects_disliked": ["Математика"],
            "subjects_easy": ["Физкультура"],
            "subjects_hard": ["Чтение"],
        },
    },
    {
        "email": "admin@test.com",
        "password": "test1234",
        "role": UserRole.admin,
        "locale": "ru",
        "profile": None,
    },
    {
        "email": "psychologist@test.com",
        "password": "test1234",
        "role": UserRole.psychologist,
        "locale": "ru",
        "profile": None,
    },
]


async def main() -> None:
    async with async_session() as db:
        for data in TEST_USERS:
            result = await db.execute(select(User).where(User.email == data["email"]))
            user = result.scalar_one_or_none()

            if user:
                print(f"  exists  {data['email']} — skipping")
                continue

            user = User(
                email=data["email"],
                hashed_password=hash_password(data["password"]),
                is_active=True,
                is_verified=True,
                role=data["role"],
                locale=data["locale"],
            )
            db.add(user)
            await db.flush()

            if data["profile"]:
                p = data["profile"]
                profile = Profile(
                    user_id=user.id,
                    name=p["name"],
                    age=p["age"],
                    grade=p["grade"],
                    city=p["city"],
                    country=p["country"],
                    language=p["language"],
                    subjects_liked=p["subjects_liked"],
                    subjects_disliked=p["subjects_disliked"],
                    subjects_easy=p["subjects_easy"],
                    subjects_hard=p["subjects_hard"],
                    age_group=compute_age_group(p["age"]),
                )
                db.add(profile)

            print(f"  created {data['email']} ({data['role'].value})")

        await db.commit()
        print("\nДone. Credentials: password=test1234 for all users.")
        print("\nUsers:")
        for u in TEST_USERS:
            profile_info = f"  [{u['profile']['name']}, {u['profile']['age']}y]" if u["profile"] else ""
            print(f"  {u['email']}{profile_info}")


if __name__ == "__main__":
    asyncio.run(main())
