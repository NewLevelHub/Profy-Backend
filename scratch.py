import asyncio
from sqlalchemy import select, delete
from app.db.session import async_session
from app.models.question import Question, QuestionInstrument

async def main():
    async with async_session() as db:
        res = await db.execute(select(Question).where(Question.instrument == QuestionInstrument.riasec))
        qs = res.scalars().all()
        print('Riasec count before:', len(qs))
        res = await db.execute(delete(Question).where(Question.instrument == QuestionInstrument.riasec))
        print('Deleted rows:', res.rowcount)
        res = await db.execute(select(Question).where(Question.instrument == QuestionInstrument.riasec))
        print('Riasec count after:', len(res.scalars().all()))

if __name__ == '__main__':
    asyncio.run(main())
