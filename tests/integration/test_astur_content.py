"""GET /assessment/{id}/astur/content — content of the bank version the open
attempt is pinned to (latest published before any attempt). No key, tier or
reviewer field ever leaks, and logical-schema concepts are served shuffled."""
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.astur_fixtures import v1_bank
from tests.integration.astur_helpers import make_student

_LEAKY_FIELDS = {
    "answer", "score_2", "score_1", "dynamic", "subject", "skill", "difficulty",
    "key_explanation", "review_status", "item_id",
}
BANK = v1_bank()


async def _content(client: AsyncClient, db: AsyncSession) -> dict:
    _, assessment, headers = await make_student(db)
    resp = await client.get(f"/api/v1/assessment/{assessment.id}/astur/content", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_content_shape_matches_the_bank_version(client: AsyncClient, db_session: AsyncSession) -> None:
    body = await _content(client, db_session)
    assert body["run_id"] is None  # no attempt opened just by looking
    assert body["bank_version"] >= 1
    assert body["lability_item_limit_ms"] == BANK.lability_item_limit_ms

    by_key = {s["key"]: s for s in body["subtests"]}
    for subtest in BANK.subtests:
        served = by_key[subtest.key]
        assert served["name"] == subtest.name["ru"]
        assert served["instruction"] == subtest.instruction["ru"]
        assert served["item_count"] == len(subtest.items) == len(served["items"])
        assert served["time_limit_sec"] == subtest.time_limit_sec
    assert by_key["lability"]["time_limit_sec"] is None


async def test_content_never_leaks_scoring_or_reviewer_fields(client: AsyncClient, db_session: AsyncSession) -> None:
    body = await _content(client, db_session)
    for subtest in body["subtests"]:
        for item in subtest["items"]:
            assert not (_LEAKY_FIELDS & item.keys()), (subtest["key"], item)


async def test_logical_schema_concepts_are_the_same_set_served_shuffled(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    body = await _content(client, db_session)
    served = next(s for s in body["subtests"] if s["key"] == "logical_schemas")["items"]
    for item, bank_item in zip(served, BANK.subtest("logical_schemas").items, strict=True):
        assert sorted(item["concepts"]) == sorted(bank_item["concepts"]["ru"])
    # The cached bank itself must never be mutated by the shuffle.
    assert v1_bank().subtest("logical_schemas").items[0]["concepts"]["ru"][0] == "живое существо"


async def test_requires_auth(client: AsyncClient, db_session: AsyncSession) -> None:
    _, assessment, _ = await make_student(db_session)
    assert (await client.get(f"/api/v1/assessment/{assessment.id}/astur/content")).status_code == 401
