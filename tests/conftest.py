from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import engine
from app.services import assessment_shared


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

    # Same issue, same fix, for the module-level Redis singleton every
    # service (assessment_shared, roadmap_builder, report_service, ...)
    # lazily creates on first use: it's bound to whichever event loop was
    # running when `get_redis()`/`_get_redis()` first constructed it, so a
    # later test's fresh loop hits "Event loop is closed" the moment it
    # tries to reuse that connection. Close it and drop the reference so the
    # next test that calls get_redis() builds a fresh client on its own
    # loop — mirrors the engine.dispose() above, just for Redis.
    if assessment_shared._redis is not None:
        await assessment_shared._redis.aclose()
        assessment_shared._redis = None
