"""Best-effort notifications (PRO-337): when the request stops waiting on
its notification budget, sends that haven't finished must keep going — not be
cancelled and silently dropped."""
import asyncio

import pytest

from app.services import psychologist_service


async def test_sends_outliving_the_budget_are_not_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(psychologist_service, "_NOTIFY_BUDGET_SECONDS", 0.05)
    delivered: list[int] = []

    async def slow_send(n: int) -> None:
        await asyncio.sleep(0.2)
        delivered.append(n)

    await psychologist_service._send_within_budget([slow_send(n) for n in range(3)])
    assert delivered == []  # the request stopped waiting...

    await asyncio.sleep(0.4)
    assert sorted(delivered) == [0, 1, 2]  # ...but every send still went out


async def test_a_failing_send_does_not_break_the_others(monkeypatch: pytest.MonkeyPatch) -> None:
    delivered: list[str] = []

    async def ok() -> None:
        delivered.append("ok")

    async def broken() -> None:
        raise RuntimeError("provider down")

    await psychologist_service._send_within_budget([broken(), ok()])
    await asyncio.sleep(0)
    assert delivered == ["ok"]
