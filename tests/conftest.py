import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app import i18n
from app.database import engine, get_db
from app.main import app as fastapi_app
from app.models.user import User
from app.services import (
    assessment_shared,
    auth_service,
    direction_inquiry_service,
    report_service,
    roadmap_builder,
)
from app.routers import auth as auth_router


@pytest.fixture(autouse=True)
def _reset_request_locale() -> AsyncGenerator[None, None]:
    """`get_current_user` (and the HTTP middleware) call `i18n.set_locale`,
    which sets a `ContextVar` without holding a reset token. In the HTTP path
    the middleware resets its own token; called directly from a test (or, later,
    a WebSocket / worker path) it would leak the value into the next test and
    make the already order-sensitive suite worse. Snapshot and restore the
    request-locale ContextVar around every test.
    """
    token = i18n._current_locale.set(i18n.DEFAULT_LOCALE)
    try:
        yield
    finally:
        i18n._current_locale.reset(token)


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


# Every module that lazily builds its own module-level `redis.asyncio.Redis`
# singleton — add new ones here when they're introduced.
_REDIS_SINGLETON_MODULES = (
    assessment_shared,
    report_service,
    roadmap_builder,
    direction_inquiry_service,
    auth_router,
)


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine_pool_per_loop() -> AsyncGenerator[None, None]:
    # pytest-asyncio opens a fresh event loop per test by default; pooled
    # asyncpg connections on app.database.engine stay bound to the loop that
    # opened them, so a connection checked out in a later test's loop breaks
    # with "another operation is in progress". Drop the pool after every
    # test so the next one opens fresh connections on its own loop.
    yield
    await engine.dispose()

    # Same issue, same fix, for every module-level Redis singleton (not just
    # assessment_shared._redis — report_service, roadmap_builder,
    # direction_inquiry_service and app.routers.auth each lazily build their
    # own): it's bound to whichever event loop was running when
    # get_redis()/_get_redis() first constructed it, so a later test's fresh
    # loop hits "Event loop is closed" the moment it tries to reuse that
    # connection. Close it and drop the reference so the next test that
    # calls get_redis() builds a fresh client on its own loop.
    for module in _REDIS_SINGLETON_MODULES:
        if module._redis is not None:
            await module._redis.aclose()
            module._redis = None

    # Redis data (unlike the DB, which each test rolls back) otherwise persists
    # across tests — notably the auth router's `_check_rate_limit` counters
    # (`register_ip:*`, `forgot_pwd_*`, `verify_*`), which accumulate over a
    # run and make a later test's first `/register` or `/forgot-password` 429.
    # Flush between tests so every test starts from clean Redis state.
    import redis.asyncio as _aioredis

    from app.config import settings as _settings

    _flush_client = _aioredis.from_url(_settings.REDIS_URL)
    try:
        await _flush_client.flushdb()
    finally:
        await _flush_client.aclose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[httpx.AsyncClient, None]:
    """HTTP client wired to the real FastAPI app, with `get_db` overridden to
    hand out the same transactional session `db_session` uses — so fixture
    setup (e.g. `test_user`) and the request under test see the same
    uncommitted data, and it's all discarded together at teardown."""

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    fastapi_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """A verified, active user — the common starting point for authenticated
    endpoint tests. Not committed: it lives in the same rolled-back
    transaction as everything else in the test."""
    user = User(
        email=f"{uuid.uuid4()}@example.test",
        hashed_password=auth_service.hash_password("Testpass123!"),
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def auth_headers(test_user: User) -> dict[str, str]:
    token = auth_service.create_jwt_token(test_user.id)
    return {"Authorization": f"Bearer {token}"}
