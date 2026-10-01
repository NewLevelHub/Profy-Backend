"""PRO-338 Ф2.6 prerequisite: GET /assessment/belbin/content — static test
content for the frontend's 7-block flow, item `role` never exposed to the
respondent (ipsative-test non-disclosure, same principle as Elers'
buffer items)."""
import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.services import auth_service
from scripts.belbin_bank import BLOCK_TOTAL, INSTRUCTION, SECTIONS


async def _auth(db: AsyncSession) -> dict:
    user = User(
        email=f"{uuid.uuid4()}@example.com", hashed_password="x",
        is_active=True, is_verified=True,
    )
    db.add(user)
    await db.flush()
    db.add(Profile(
        user_id=user.id, name="Т", age=16, grade=10, city="Алматы",
        country="Казахстан", language="ru", age_group=AgeGroup.senior,
    ))
    await db.flush()
    return {"Authorization": f"Bearer {auth_service.create_jwt_token(user.id)}"}


async def test_content_shape_matches_the_bank(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _auth(db_session)

    resp = await client.get("/api/v1/assessment/belbin/content", headers=headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    # `INSTRUCTION`/section `title`/item `text` are `{ru,kk}` dicts (PRO-338
    # Ф4.4); the response resolves to the caller's locale — `ru` by default.
    assert body["instruction"] == INSTRUCTION["ru"]
    assert body["block_total"] == BLOCK_TOTAL == 10
    assert len(body["sections"]) == 7
    for section, expected in zip(body["sections"], SECTIONS, strict=True):
        assert section["section"] == expected["section"]
        assert section["title"] == expected["title"]["ru"]
        assert len(section["items"]) == 8
        assert [i["id"] for i in section["items"]] == [i["id"] for i in expected["items"]]
        assert [i["text"] for i in section["items"]] == [i["text"]["ru"] for i in expected["items"]]


async def test_content_never_leaks_the_role_key(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _auth(db_session)

    resp = await client.get("/api/v1/assessment/belbin/content", headers=headers)

    body = resp.json()
    for section in body["sections"]:
        for item in section["items"]:
            assert set(item.keys()) == {"id", "text"}


async def test_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/assessment/belbin/content")
    assert resp.status_code == 401
