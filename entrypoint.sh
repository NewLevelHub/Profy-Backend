#!/usr/bin/env bash
set -euo pipefail

echo "==> Running migrations..."
alembic upgrade head

echo "==> Seeding akinator content & directions..."
python scripts/seed_akinator_content.py

echo "==> Seeding subject questions..."
python scripts/seed_subject_questions.py

echo "==> Seeding universities (global)..."
python scripts/seed_universities.py

echo "==> Seeding Astana universities..."
python scripts/seed_astana_universities.py

echo "==> Seeding Almaty universities..."
python scripts/seed_almaty_universities.py

echo "==> Cleaning broken subject readiness sessions..."
python - <<'PYEOF'
import asyncio, sys
sys.path.insert(0, '.')
from app.database import async_session
from app.models.subject_readiness_session import SubjectReadinessSession
from sqlalchemy import delete

async def main():
    async with async_session() as db:
        result = await db.execute(
            delete(SubjectReadinessSession)
            .where(SubjectReadinessSession.question_ids == [])
        )
        await db.commit()
        if result.rowcount:
            print(f"  Deleted {result.rowcount} broken session(s)")

asyncio.run(main())
PYEOF

echo "==> Validating content integrity..."
python scripts/validate_content_integrity.py

echo "==> Starting API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
