import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select, func
from app.database import async_session
from app.models.program import Program

async def main():
    async with async_session() as db:
        res = await db.execute(select(Program.cost_currency, func.count(Program.id)).group_by(Program.cost_currency))
        for row in res.all():
            print(f"Currency: {row[0]}, Count: {row[1]}")

if __name__ == '__main__':
    asyncio.run(main())
