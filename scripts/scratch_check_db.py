import asyncio
import os
import sys
import json

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select
from sqlalchemy.orm import joinedload
from app.database import async_session
from app.models.program import Program
from app.models.university import University

async def main():
    async with async_session() as db:
        res = await db.execute(select(Program).options(joinedload(Program.university)).where(Program.requirements != None))
        programs = res.scalars().all()
        count = 0
        for p in programs:
            if 'admission_scores_2026' in p.requirements:
                print(f"Program: {p.name} (University: {p.university.name}, OVPO: {p.university.ovpo_code})")
                print("Requirements:")
                print(json.dumps(p.requirements, indent=2, ensure_ascii=False))
                print("Fact Sources:")
                print(json.dumps(p.fact_sources, indent=2, ensure_ascii=False))
                print("-" * 50)
                count += 1
                if count >= 3:
                    break

if __name__ == '__main__':
    asyncio.run(main())
