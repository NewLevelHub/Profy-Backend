from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import engine


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Async DB session isolated per test.

    Binds the session to a single connection wrapped in an outer transaction,
    and joins it as a SAVEPOINT (join_transaction_mode="create_savepoint") so
    that code under test calling session.commit() only releases the
    savepoint instead of committing for real. The outer transaction is
    always rolled back on teardown, so nothing written during a test
    survives it — reuse this fixture instead of hand-rolling setup/cleanup.
    """
    async with engine.connect() as conn:
        outer_trans = await conn.begin()
        session = AsyncSession(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        try:
            yield session
        finally:
            await session.close()
            await outer_trans.rollback()


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine_pool_per_loop() -> AsyncGenerator[None, None]:
    # pytest-asyncio opens a fresh event loop per test by default; pooled
    # asyncpg connections on app.database.engine stay bound to the loop that
    # opened them, so a connection checked out in a later test's loop breaks
    # with "another operation is in progress". Drop the pool after every
    # test so the next one opens fresh connections on its own loop.
    yield
    await engine.dispose()
