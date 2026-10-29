import uuid
from collections.abc import AsyncGenerator, Generator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app import i18n
from app.config import settings
from app.database import engine, get_db
from app.main import app as fastapi_app
from app.models.crm import CrmTariff
from app.models.user import User, UserRole
from app.services import (
    assessment_shared,
    auth_service,
    report_service,
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


@pytest.fixture(autouse=True)
def _no_mail_domain_lookup(monkeypatch) -> None:
    """Invitations check the email domain over DNS; tests invite
    `@example.com` (a null-MX domain) and may run offline. Tests of the
    check itself turn it back on and stub the lookup."""
    monkeypatch.setattr(settings, "INVITATION_CHECK_DELIVERABILITY", False)


@pytest.fixture(autouse=True)
def _no_real_email(monkeypatch) -> None:
    """Tests never send real email, whatever the mounted .env holds (a dev
    .env may carry live SES or Resend keys — mail to the tests' made-up
    addresses would bounce and hurt the sender's reputation). With no
    provider credentials email_service skips sending; tests that check an
    email mock the send function itself. The provider is the code default
    (Resend) — tests of SES select it themselves."""
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "resend")
    monkeypatch.setattr(settings, "RESEND_API_KEY", "")
    monkeypatch.setattr(settings, "SES_ACCESS_KEY_ID", "")
    monkeypatch.setattr(settings, "SES_SECRET_ACCESS_KEY", "")


@pytest.fixture(autouse=True)
def _no_real_telegram(monkeypatch) -> None:
    """Tests never write to Telegram, whatever the mounted .env holds: the
    tests share the dev database, where a real specialist may have linked a
    real chat. The bot is off unless a test turns it on (with the client
    mocked); Bot API calls raise in any case."""
    from app.services.telegram import client as telegram_client

    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(settings, "TELEGRAM_BOT_USERNAME", "")
    monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_SECRET", "")

    def _blocked(method: str) -> str:
        raise AssertionError(f"a test reached the real Telegram Bot API ({method}); mock telegram.client")

    # Every Bot API call builds its URL here first.
    monkeypatch.setattr(telegram_client, "_url", _blocked)


@pytest.fixture(autouse=True)
def _no_real_meta(monkeypatch) -> None:
    """Tests never call the Meta Marketing API, whatever the mounted .env
    holds: off unless a test turns it on with the client mocked; a real
    request raises in any case."""
    from app.services.meta_ads import client as meta_client

    monkeypatch.setattr(settings, "META_ACCESS_TOKEN", "")
    monkeypatch.setattr(settings, "META_AD_ACCOUNT_ID", "")

    async def _blocked(*_args, **_kwargs):
        raise AssertionError("a test reached the real Meta Marketing API; mock meta_ads.client")

    monkeypatch.setattr(meta_client, "_get", _blocked)


@pytest.fixture(autouse=True)
def _no_real_whatsapp(monkeypatch) -> Generator[None, None, None]:
    """Tests never write to WhatsApp, whatever the mounted .env holds: off
    unless a test turns it on with the stub provider (tests/integration/
    test_crm_whatsapp.py); a Green API URL raises in any case."""
    from app.services.whatsapp import green_api, provider

    monkeypatch.setattr(settings, "GREEN_API_ID_INSTANCE", "")
    monkeypatch.setattr(settings, "GREEN_API_TOKEN_INSTANCE", "")
    monkeypatch.setattr(settings, "GREEN_API_WEBHOOK_TOKEN", "")
    monkeypatch.setattr(settings, "WHATSAPP_TEST_NUMBERS", "")

    def _blocked(*_args, **_kwargs):
        raise AssertionError("a test reached the real Green API; use the stub provider")

    monkeypatch.setattr(green_api, "_url", _blocked)
    yield
    provider.use(None)


@pytest.fixture(autouse=True)
def _open_registration(monkeypatch) -> None:
    """Most auth tests sign up without a CRM invite. The invite-only rule has
    its own tests (test_crm_student_progress.py), which turn it back on."""
    monkeypatch.setattr(settings, "REGISTRATION_INVITE_ONLY", False)


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
    # assessment_shared._redis — report_service and app.routers.auth each
    # lazily build their own): it's bound to whichever event loop was running when
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
    # (`register_ip:*`, `login_*`, `forgot_pwd_*`, `verify_*`), which accumulate
    # over a run and make a later test's first `/register` or `/forgot-password` 429.
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


# The seeded price list as the migrations made it. The owner edits it in the
# CRM, and the tests run against that same database, inside a transaction
# that is rolled back: they must not depend on what the owner did with it.
# «Тестирование» without the psychologist, «Пакет» with them (1469e5b6dfbb).
SEEDED_TARIFFS = {"testing": False, "package": True}


@pytest_asyncio.fixture
async def price_list(db_session: AsyncSession) -> None:
    for code, review in SEEDED_TARIFFS.items():
        await db_session.execute(
            update(CrmTariff).where(CrmTariff.code == code).values(active=True, psychologist_review=review)
        )


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
    token = auth_service.create_jwt_token(test_user)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    user = User(
        email=f"{uuid.uuid4()}@example.test",
        hashed_password=auth_service.hash_password("Testpass123!"),
        is_active=True,
        is_verified=True,
        role=UserRole.admin,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def admin_headers(admin_user: User) -> dict[str, str]:
    token = auth_service.create_jwt_token(admin_user)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def psychologist_user(db_session: AsyncSession) -> User:
    user = User(
        email=f"{uuid.uuid4()}@example.test",
        hashed_password=auth_service.hash_password("Testpass123!"),
        is_active=True,
        is_verified=True,
        role=UserRole.psychologist,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def psychologist_headers(psychologist_user: User) -> dict[str, str]:
    token = auth_service.create_jwt_token(psychologist_user)
    return {"Authorization": f"Bearer {token}"}
