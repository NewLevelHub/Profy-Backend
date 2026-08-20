import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select
from sqlalchemy.orm import joinedload
from app.database import async_session
from app.models.program import Program
from app.models.university import University

async def main():
    async with async_session() as db:
        res = await db.execute(
            select(Program)
            .options(joinedload(Program.university))
            .join(University)
            .where(University.name.like('%Туран%'))
        )
        programs = res.scalars().all()
        for p in programs:
            print(f"Program: {p.name} (University: {p.university.name})")
            print(f"  Cost Per Year: {p.cost_per_year}")
            print(f"  Cost Label: {p.cost_label}")
            print(f"  Cost Per Year Min: {p.cost_per_year_min}")
            print(f"  Cost Per Year Max: {p.cost_per_year_max}")
            print(f"  Description: {p.description}")
            print("-" * 50)

if __name__ == '__main__':
    asyncio.run(main())
