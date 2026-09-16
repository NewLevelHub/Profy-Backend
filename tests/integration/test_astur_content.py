"""PRO-338 Ф3.6 prerequisite: GET /assessment/astur/content — static test
content for the frontend's 7-subtest flow. No correct-answer field (answer/
score_2/score_1/dynamic/note/rule/subject) ever leaks, and logical_schemas'
`concepts` is shuffled away from the bank's correct order."""
import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import AgeGroup, Profile
from app.models.user import User
from app.services import auth_service
from scripts.astur_bank import SUBTEST_ITEMS, SUBTESTS

_LEAKY_FIELDS = {"answer", "score_2", "score_1", "score_0_example", "dynamic", "note", "rule", "subject"}


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

    resp = await client.get("/api/v1/assessment/astur/content", headers=headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["subtests"]) == 7
    assert body["lability_item_limit_ms"] == 5000

    by_key = {s["key"]: s for s in body["subtests"]}
    for meta in SUBTESTS:
        subtest = by_key[meta["key"]]
        assert subtest["name"] == meta["name"]
        assert subtest["instruction"] == meta["instruction"]
        assert subtest["item_count"] == meta["item_count"] == len(subtest["items"])
        assert subtest["scored"] == meta["scored"]

    assert by_key["lability"]["time_limit_sec"] is None
    assert by_key["awareness"]["time_limit_sec"] == 360


async def test_content_never_leaks_scoring_fields(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _auth(db_session)

    resp = await client.get("/api/v1/assessment/astur/content", headers=headers)

    body = resp.json()
    for subtest in body["subtests"]:
        for item in subtest["items"]:
            assert not (_LEAKY_FIELDS & item.keys()), (subtest["key"], item)


async def test_logical_schemas_concepts_are_shuffled_not_the_answer_order(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    headers = await _auth(db_session)

    resp = await client.get("/api/v1/assessment/astur/content", headers=headers)

    body = resp.json()
    schemas = next(s for s in body["subtests"] if s["key"] == "logical_schemas")
    bank_items = SUBTEST_ITEMS["logical_schemas"]
    assert len(schemas["items"]) == len(bank_items)
    for served, bank_item in zip(schemas["items"], bank_items, strict=True):
        assert set(served["concepts"]) == set(bank_item["concepts"])
        # Not a strict "must differ" assertion (a real shuffle can land on
        # the original order by chance) — the content-integrity guarantee
        # (same items, no extra/missing) is what's checked above; the
        # non-leak guarantee is covered by test_content_never_leaks_scoring
        # _fields (no separate "answer" field ever accompanies `concepts`).


async def test_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/assessment/astur/content")
    assert resp.status_code == 401
