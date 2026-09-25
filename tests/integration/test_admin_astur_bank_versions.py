"""PRO-427 — admin АСТУР bank versions: draft → validate → publish →
immutable, key confirmations, diff, per-item analytics, and the old
free-form content override being closed for АСТУР."""
import copy

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.astur_helpers import complete_attempt, make_student, v1_version_id
from tests.unit.test_astur_bank import reviewed

BASE = "/api/v1/admin/astur/bank-versions"


def _first_awareness(document: dict) -> dict:
    return next(s for s in document["subtests"] if s["key"] == "awareness")["items"][0]


async def _draft(client: AsyncClient, headers: dict) -> dict:
    resp = await client.post(f"{BASE}/draft", headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _put(client: AsyncClient, headers: dict, draft: dict, document: dict):
    return await client.put(f"{BASE}/{draft['id']}", json={"document": document, "notes": "t"}, headers=headers)


async def test_v1_is_listed_as_published(client: AsyncClient, admin_headers: dict) -> None:
    resp = await client.get(BASE, headers=admin_headers)
    assert resp.status_code == 200
    v1 = next(v for v in resp.json()["items"] if v["version"] == 1)
    assert v1["status"] == "published"
    assert v1["item_count"] == 103
    assert len(v1["content_hash"]) == 64


async def test_draft_is_branched_from_latest_published_and_is_single(
    client: AsyncClient, admin_headers: dict, db_session: AsyncSession
) -> None:
    first = await _draft(client, admin_headers)
    second = await _draft(client, admin_headers)
    assert first["id"] == second["id"]
    assert first["status"] == "draft" and first["version"] is None
    # v1 predates review metadata: every new version must add it first.
    assert {i["code"] for i in first["issues"]} == {"review_required"}
    assert first["key_changed_item_ids"] == []
    assert first["has_changes"] is False


async def test_unchanged_draft_cannot_be_published(client: AsyncClient, admin_headers: dict) -> None:
    draft = await _draft(client, admin_headers)
    resp = await client.post(f"{BASE}/{draft['id']}/publish", json={}, headers=admin_headers)
    assert resp.status_code == 409


async def test_changed_key_must_be_confirmed_then_publishes_an_immutable_version(
    client: AsyncClient, admin_headers: dict
) -> None:
    draft = await _draft(client, admin_headers)
    document = reviewed(draft["document"])
    item = _first_awareness(document)
    item["options"] = {"ru": ["один", "два"], "kk": ["бір", "екі"]}
    item["answer"] = {"ru": "два", "kk": "екі"}
    updated = (await _put(client, admin_headers, draft, document)).json()
    assert updated["key_changed_item_ids"] == [item["item_id"]]
    assert updated["issues"] == []

    rejected = await client.post(f"{BASE}/{draft['id']}/publish", json={}, headers=admin_headers)
    assert rejected.status_code == 422
    assert {i["code"] for i in rejected.json()["detail"]["issues"]} == {"key_confirmation_required"}

    published = await client.post(
        f"{BASE}/{draft['id']}/publish", json={"confirmed_item_ids": [item["item_id"]]}, headers=admin_headers
    )
    assert published.status_code == 200, published.text
    body = published.json()
    assert body["status"] == "published" and body["version"] >= 2

    # Published is immutable.
    assert (await _put(client, admin_headers, draft, document)).status_code == 409
    assert (await client.delete(f"{BASE}/{draft['id']}", headers=admin_headers)).status_code == 409


async def test_key_outside_options_cannot_be_published(client: AsyncClient, admin_headers: dict) -> None:
    draft = await _draft(client, admin_headers)
    document = copy.deepcopy(draft["document"])
    item = _first_awareness(document)
    item["answer"] = {"ru": "несуществующий", "kk": "жоқ нұсқа"}
    updated = (await _put(client, admin_headers, draft, document)).json()
    assert "key_not_in_options" in {i["code"] for i in updated["issues"]}

    resp = await client.post(
        f"{BASE}/{draft['id']}/publish", json={"confirmed_item_ids": [item["item_id"]]}, headers=admin_headers
    )
    assert resp.status_code == 422
    assert "key_not_in_options" in {i["code"] for i in resp.json()["detail"]["issues"]}


async def test_diff_lists_changed_items_against_the_base(client: AsyncClient, admin_headers: dict) -> None:
    draft = await _draft(client, admin_headers)
    document = copy.deepcopy(draft["document"])
    _first_awareness(document)["text"]["ru"] = "Новая формулировка …?"
    await _put(client, admin_headers, draft, document)

    diff = (await client.get(f"{BASE}/{draft['id']}/diff", headers=admin_headers)).json()
    assert diff["from_version"] is not None and diff["to_version"] is None
    assert diff["changes"] == [
        {"kind": "changed", "subtest": "awareness", "item_id": "awareness-01", "fields": ["text"]}
    ]


async def test_draft_can_be_discarded(client: AsyncClient, admin_headers: dict) -> None:
    draft = await _draft(client, admin_headers)
    assert (await client.delete(f"{BASE}/{draft['id']}", headers=admin_headers)).status_code == 204
    assert (await client.get(f"{BASE}/{draft['id']}", headers=admin_headers)).status_code == 404


async def test_item_analytics_by_version_and_age_band(
    client: AsyncClient, admin_headers: dict, db_session: AsyncSession
) -> None:
    _, assessment, headers = await make_student(db_session, age=14, grade=8)
    await complete_attempt(client, assessment.id, headers, wrong={"awareness"})
    version_id = await v1_version_id(db_session)

    body = (await client.get(f"{BASE}/{version_id}/analytics?age_band=14_15", headers=admin_headers)).json()
    assert body["bank_version"] == 1
    assert body["attempts"] >= 1
    assert body["age_bands"]["14_15"] >= 1
    awareness = next(s for s in body["subtests"] if s["key"] == "awareness")
    first = awareness["items"][0]
    assert first["item_id"] == "awareness-01"
    assert first["mean_score_share"] is not None
    assert len(first["option_counts"]) == 5

    filtered = (await client.get(f"{BASE}/{version_id}/analytics?grade=8", headers=admin_headers)).json()
    assert filtered["filters"] == {"age_band": None, "grade": 8}
    # JSON object keys are strings; `grades` counts every attempt of the version.
    assert filtered["attempts"] == filtered["grades"]["8"] >= 1


async def test_astur_content_override_is_closed(client: AsyncClient, admin_headers: dict) -> None:
    resp = await client.put(
        "/api/v1/admin/content-overrides/astur", json={"content_ru": {"subtests": []}}, headers=admin_headers
    )
    assert resp.status_code == 409


async def test_non_admin_is_forbidden(client: AsyncClient, auth_headers: dict) -> None:
    assert (await client.get(BASE, headers=auth_headers)).status_code == 403


async def test_unrecognized_answer_can_be_added_to_the_next_draft(client: AsyncClient, admin_headers: dict) -> None:
    resp = await client.post(
        f"{BASE}/draft/synonyms",
        json={"item_id": "generalization-01", "tier": "score_1", "locale": "ru", "text": "  зелёные   растения "},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    draft = resp.json()
    assert draft["status"] == "draft"
    item = next(s for s in draft["document"]["subtests"] if s["key"] == "generalization")["items"][0]
    assert item["score_1"]["ru"][-1] == "зелёные растения"

    again = await client.post(
        f"{BASE}/draft/synonyms",
        json={"item_id": "generalization-01", "tier": "score_2", "locale": "ru", "text": "Зелёные растения"},
        headers=admin_headers,
    )
    assert again.status_code == 409
    wrong_item = await client.post(
        f"{BASE}/draft/synonyms",
        json={"item_id": "awareness-01", "tier": "score_1", "locale": "ru", "text": "x"},
        headers=admin_headers,
    )
    assert wrong_item.status_code == 404
