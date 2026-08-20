"""Proves the `_dispose_engine_pool_per_loop` autouse fixture in conftest.py
resets every module's Redis singleton, not just `assessment_shared._redis`:
each test gets its own event loop, and a `redis.asyncio.Redis` client bound
to a *previous* test's (now-closed) loop raises on use. If `report_service`
were left out of that fixture's cleanup list, one of these two tests —
whichever runs second — would fail with a closed-event-loop error instead
of a normal assertion. Order matters here, so this isn't parametrized into
one test."""

from app.services import report_service


async def test_first_test_binds_a_redis_client_to_its_own_loop() -> None:
    redis = report_service._get_redis()
    assert await redis.ping() is True


async def test_second_test_gets_a_fresh_client_not_the_previous_loops() -> None:
    # If conftest.py did NOT reset report_service._redis after the previous
    # test, this would reuse its client — bound to a loop that
    # pytest-asyncio already closed — and raise instead of returning True.
    redis = report_service._get_redis()
    assert await redis.ping() is True
