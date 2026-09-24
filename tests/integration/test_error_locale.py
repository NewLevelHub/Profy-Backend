"""KZ-309 — user-facing Russian `detail=` errors now also carry a stable
machine `error_code` (contract §7).

Policy: the backend keeps the Russian `detail` string byte-for-byte (backward
compat) and *adds* `error_code` next to it; the frontend localizes from a dict
keyed by `error_code` (KZ-203). These tests assert the response shape and that
`detail` is unchanged.
"""

import uuid

import httpx
import pytest
from fastapi import FastAPI, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.main import app_error_handler
from app.models.assessment import Assessment, AssessmentGoal
from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.services import auth_service, llm_client


async def test_app_error_handler_emits_detail_and_error_code() -> None:
    sub = FastAPI()
    sub.add_exception_handler(AppError, app_error_handler)

    @sub.get("/boom")
    async def _boom() -> None:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            error_code="assessment_not_completed",
            detail="Тест ещё не завершён — сначала ответь на все обязательные вопросы",
        )

    transport = httpx.ASGITransport(app=sub)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.get("/boom")

    assert resp.status_code == 409
    assert resp.json() == {
        "detail": "Тест ещё не завершён — сначала ответь на все обязательные вопросы",
        "error_code": "assessment_not_completed",
    }


def test_app_error_is_an_httpexception_subclass() -> None:
    from fastapi import HTTPException

    err = AppError(status_code=400, error_code="x", detail="ru")
    assert isinstance(err, HTTPException)
    assert err.detail == "ru"
    assert err.error_code == "x"


async def test_age_gate_error_carries_code_and_unchanged_detail(
    client: httpx.AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The LLM check runs before the age gate — switch it on so the request
    # reaches the gate without a real key (nothing is generated: it 403s first).
    monkeypatch.setattr(llm_client, "is_enabled", lambda: True)

    user = User(
        email=f"kz309-{uuid.uuid4()}@example.com",
        hashed_password="x",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    profile = Profile(
        user_id=user.id,
        name="Тест",
        age=9,
        grade=3,
        city="Алматы",
        country="Казахстан",
        language="ru",
        age_group=AgeGroup.junior,
    )
    db_session.add(profile)
    await db_session.flush()

    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db_session.add(assessment)
    await db_session.flush()
    await db_session.commit()

    headers = {"Authorization": f"Bearer {auth_service.create_jwt_token(user.id)}"}
    resp = await client.post(
        "/api/v1/roadmap/direction",
        json={"assessment_id": str(assessment.id), "direction_slug": "developer"},
        headers=headers,
    )

    assert resp.status_code == 403
    body = resp.json()
    assert body["error_code"] == "feature_requires_age_10"
    # detail stays the exact pre-KZ-309 Russian string
    assert body["detail"] == "Эта возможность доступна с 10 лет"
