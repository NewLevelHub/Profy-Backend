"""Login brute-force and credential-stuffing protection."""

from app.i18n.catalog import api_errors
from app.routers import auth as auth_router


async def _clear_rate_limits() -> None:
    # Redis is not transactional like the database fixture. Clear explicitly
    # so this module is deterministic even when run alone after a dev session.
    await auth_router._get_redis().flushdb()


async def test_login_limits_normalized_email_without_exposing_it_in_redis(
    client,
    monkeypatch,
):
    await _clear_rate_limits()
    monkeypatch.setattr(auth_router, "_LOGIN_EMAIL_LIMIT", 2)
    monkeypatch.setattr(auth_router, "_LOGIN_IP_LIMIT", 100)

    attempts = ["Student@Example.com", "student@example.COM", "STUDENT@example.com"]
    responses = []
    for email in attempts:
        responses.append(
            await client.post(
                "/api/v1/auth/login",
                headers={"Accept-Language": "kk"},
                json={"email": email, "password": "wrong-password"},
            )
        )

    assert [response.status_code for response in responses] == [401, 401, 429]
    assert responses[-1].json() == {"detail": api_errors.KK["rate_limit_exceeded"]}
    assert (
        1
        <= int(responses[-1].headers["Retry-After"])
        <= auth_router._LOGIN_EMAIL_WINDOW
    )

    email_keys = await auth_router._get_redis().keys("login_email:*")
    assert len(email_keys) == 1
    assert "student@example.com" not in email_keys[0]


async def test_successful_login_clears_consecutive_email_failures(
    client,
    db_session,
    test_user,
    monkeypatch,
):
    await _clear_rate_limits()
    monkeypatch.setattr(auth_router, "_LOGIN_EMAIL_LIMIT", 2)
    monkeypatch.setattr(auth_router, "_LOGIN_IP_LIMIT", 100)
    url = "/api/v1/auth/login"
    test_user.email = f"{test_user.id}@example.com"
    await db_session.flush()

    first_success = await client.post(
        url,
        json={"email": test_user.email, "password": "Testpass123!"},
    )
    assert first_success.status_code == 200
    assert await auth_router._get_redis().keys("login_ip:*") == []

    failed = await client.post(
        url,
        json={"email": test_user.email, "password": "wrong-password"},
    )
    succeeded = await client.post(
        url,
        json={"email": test_user.email, "password": "Testpass123!"},
    )

    assert failed.status_code == 401
    assert succeeded.status_code == 200
    assert not await auth_router._get_redis().exists(
        auth_router._login_email_rate_key(test_user.email)
    )

    after_success = []
    for _ in range(3):
        after_success.append(
            await client.post(
                url,
                json={"email": test_user.email, "password": "wrong-password"},
            )
        )
    assert [response.status_code for response in after_success] == [401, 401, 429]


async def test_login_ip_limit_blocks_attempts_across_different_accounts(
    client,
    monkeypatch,
):
    await _clear_rate_limits()
    monkeypatch.setattr(auth_router, "_LOGIN_IP_LIMIT", 2)
    monkeypatch.setattr(auth_router, "_LOGIN_EMAIL_LIMIT", 100)

    responses = []
    for index in range(3):
        responses.append(
            await client.post(
                "/api/v1/auth/login",
                json={
                    "email": f"unknown-{index}@example.com",
                    "password": "wrong-password",
                },
            )
        )

    assert [response.status_code for response in responses] == [401, 401, 429]
    ip_keys = await auth_router._get_redis().keys("login_ip:*")
    assert len(ip_keys) == 1
    assert "127.0.0.1" not in ip_keys[0]
