"""POST /assessment/{id}/astur/attempt — content of the bank version and
locale the opened attempt is pinned to. No key, tier or reviewer field ever
leaks, figure stimuli are addressed by item_id, and logical-schema concepts
are served shuffled."""
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.astur_fixtures import v1_bank
from tests.integration.astur_helpers import make_student, open_attempt

_LEAKY_FIELDS = {
    "answer", "score_2", "score_1", "dynamic", "subject", "skill", "difficulty",
    "key_explanation", "review_status",
}
BANK = v1_bank()


async def _content(client: AsyncClient, db: AsyncSession) -> dict:
    _, assessment, headers = await make_student(db)
    return (await open_attempt(client, assessment.id, headers))["content"]


async def test_content_shape_matches_the_bank_version(client: AsyncClient, db_session: AsyncSession) -> None:
    body = await _content(client, db_session)
    assert body["run_id"] is not None
    assert body["bank_version"] >= 1
    assert body["locale"] == "ru"
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


async def test_figure_stimuli_are_addressed_by_item_id(client: AsyncClient, db_session: AsyncSession) -> None:
    body = await _content(client, db_session)
    figures = next(s for s in body["subtests"] if s["key"] == "geometric_figures")["items"]
    for item in figures:
        stimulus = item["stimulus"]
        assert stimulus["target"] == f"astur-figures/v1/{item['item_id']}-target.png"
        assert set(stimulus["options"]) == {"А", "Б", "В", "Г"}


async def test_requires_auth(client: AsyncClient, db_session: AsyncSession) -> None:
    _, assessment, _ = await make_student(db_session)
    assert (await client.post(f"/api/v1/assessment/{assessment.id}/astur/attempt", json={})).status_code == 401
