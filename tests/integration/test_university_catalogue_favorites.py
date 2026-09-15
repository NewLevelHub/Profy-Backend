"""Coverage for the standalone university catalogue and favourites (PRO-265).

Three things are worth pinning down here and are easy to break later:
starring is idempotent (the UI fires PUT on every click, including a
double one); a starred university leads both the catalogue and the
direction-scoped program picker; and neither endpoint regresses for an
anonymous caller, since both were public before favourites existed.
"""

import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.direction import Direction
from app.models.program import Program
from app.models.university import University


def _university(name: str, *, country: str, city: str, ranking: int | None) -> University:
    return University(
        name=name,
        slug=f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}",
        country=country,
        city=city,
        ranking=ranking,
        aliases=[],
    )


@pytest.fixture
async def universities(db_session: AsyncSession) -> list[University]:
    """Three universities with a deliberate ranking order: top, middle, unranked.

    They get their own one-off country names, and every assertion below
    filters on those. The test DB is the real, seeded one (~250 universities)
    — asserting on the unfiltered catalogue would be asserting on seed data,
    and would start failing the next time a university is added to it.
    """
    marker = uuid.uuid4().hex[:8]
    main_country = f"Тестландия-{marker}"
    other_country = f"Иноземье-{marker}"
    rows = [
        _university("Alpha Institute", country=main_country, city="Астана", ranking=1),
        _university("Beta University", country=main_country, city=f"Алматы-{marker}", ranking=50),
        _university("Gamma College", country=other_country, city="Берлин", ranking=None),
    ]
    rows[1].aliases = [f"БетаУни-{marker}"]
    rows[1].short_name = f"BetaU-{marker}"
    db_session.add_all(rows)
    await db_session.flush()
    return rows


def _countries(universities: list[University]) -> tuple[str, str]:
    """(country shared by the first two, country of the third)."""
    return universities[0].country, universities[2].country


async def test_catalogue_lists_and_paginates(
    client: httpx.AsyncClient, universities: list[University]
) -> None:
    main_country, _ = _countries(universities)

    first = await client.get(
        "/api/v1/universities", params={"country": main_country, "limit": 1}
    )
    assert first.status_code == 200
    body = first.json()
    assert body == {
        "items": body["items"],
        "total": 2,
        "page": 1,
        "limit": 1,
    }
    assert [item["name"] for item in body["items"]] == ["Alpha Institute"]
    # Anonymous callers get the plain catalogue-quality order and no favourites.
    assert body["items"][0]["is_favorite"] is False

    second = await client.get(
        "/api/v1/universities", params={"country": main_country, "limit": 1, "page": 2}
    )
    assert [item["name"] for item in second.json()["items"]] == ["Beta University"]


async def test_search_matches_alias_short_name_and_city(
    client: httpx.AsyncClient, universities: list[University]
) -> None:
    marker = universities[1].aliases[0].split("-")[-1]
    for term in (f"БетаУни-{marker}", f"BetaU-{marker}", f"Алматы-{marker}"):
        response = await client.get("/api/v1/universities", params={"search": term})
        assert response.status_code == 200, term
        names = [item["name"] for item in response.json()["items"]]
        assert "Beta University" in names, term


async def test_country_filter_and_countries_endpoint(
    client: httpx.AsyncClient, universities: list[University]
) -> None:
    main_country, other_country = _countries(universities)

    response = await client.get("/api/v1/universities", params={"country": other_country})
    assert response.status_code == 200
    assert [item["name"] for item in response.json()["items"]] == ["Gamma College"]

    countries = await client.get("/api/v1/universities/countries")
    assert countries.status_code == 200
    counts = {row["country"]: row["count"] for row in countries.json()}
    assert counts[main_country] == 2
    assert counts[other_country] == 1


async def test_starring_is_idempotent_and_floats_to_the_top(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    universities: list[University],
) -> None:
    main_country, _ = _countries(universities)
    unranked = universities[1]  # Beta University — ranked 50, so normally second
    params = {"country": main_country}

    before = await client.get("/api/v1/universities", params=params, headers=auth_headers)
    assert [i["name"] for i in before.json()["items"]] == ["Alpha Institute", "Beta University"]

    first = await client.put(f"/api/v1/universities/{unranked.id}/favorite", headers=auth_headers)
    assert first.status_code == 204
    # The UI fires this on every click; a second one must not 409 or 500.
    second = await client.put(f"/api/v1/universities/{unranked.id}/favorite", headers=auth_headers)
    assert second.status_code == 204

    after = await client.get("/api/v1/universities", params=params, headers=auth_headers)
    items = after.json()["items"]
    assert [i["name"] for i in items] == ["Beta University", "Alpha Institute"]
    assert items[0]["is_favorite"] is True
    assert items[1]["is_favorite"] is False

    only = await client.get(
        "/api/v1/universities",
        params={**params, "only_favorites": True},
        headers=auth_headers,
    )
    assert [item["name"] for item in only.json()["items"]] == ["Beta University"]

    # Unstarring is idempotent for the same reason.
    assert (
        await client.delete(f"/api/v1/universities/{unranked.id}/favorite", headers=auth_headers)
    ).status_code == 204
    assert (
        await client.delete(f"/api/v1/universities/{unranked.id}/favorite", headers=auth_headers)
    ).status_code == 204

    cleared = await client.get(
        "/api/v1/universities",
        params={**params, "only_favorites": True},
        headers=auth_headers,
    )
    assert cleared.json()["total"] == 0


async def test_favorites_do_not_leak_to_anonymous_callers(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    universities: list[University],
) -> None:
    main_country, _ = _countries(universities)
    await client.put(f"/api/v1/universities/{universities[1].id}/favorite", headers=auth_headers)

    anonymous = await client.get("/api/v1/universities", params={"country": main_country})
    items = anonymous.json()["items"]
    assert all(item["is_favorite"] is False for item in items)
    # Ordering is untouched too — no star means pure catalogue-quality order.
    assert [i["name"] for i in items] == ["Alpha Institute", "Beta University"]

    # only_favorites without a token is an empty page, not an error.
    empty = await client.get("/api/v1/universities", params={"only_favorites": True})
    assert empty.status_code == 200
    assert empty.json()["total"] == 0


async def test_starring_an_unknown_university_is_404(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.put(
        f"/api/v1/universities/{uuid.uuid4()}/favorite", headers=auth_headers
    )
    assert response.status_code == 404


async def test_favorite_requires_authentication(
    client: httpx.AsyncClient, universities: list[University]
) -> None:
    response = await client.put(f"/api/v1/universities/{universities[0].id}/favorite")
    assert response.status_code == 401


async def test_detail_returns_programs_and_favorite_flag(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    universities: list[University],
) -> None:
    university = universities[0]
    db_session.add(Program(university_id=university.id, name="Информатика", language="ru"))
    await db_session.flush()

    response = await client.get(f"/api/v1/universities/{university.id}", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["is_favorite"] is False
    assert [p["name"] for p in body["programs"]] == ["Информатика"]

    await client.put(f"/api/v1/universities/{university.id}/favorite", headers=auth_headers)
    starred = await client.get(f"/api/v1/universities/{university.id}", headers=auth_headers)
    assert starred.json()["is_favorite"] is True

    missing = await client.get(f"/api/v1/universities/{uuid.uuid4()}")
    assert missing.status_code == 404


async def test_program_picker_puts_starred_universities_first(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    universities: list[University],
) -> None:
    direction = Direction(
        slug=f"test-dir-{uuid.uuid4().hex[:6]}",
        name="Тестовое направление",
        holland_code="RIA",
    )
    db_session.add(direction)
    await db_session.flush()

    for university in universities:
        program = Program(university_id=university.id, name=f"Программа {university.name}", language="ru")
        program.directions.append(direction)
        db_session.add(program)
    await db_session.flush()

    params = {"profession": direction.slug, "limit": 10}

    anonymous = await client.get("/api/v1/universities/programs", params=params)
    assert anonymous.status_code == 200
    anon_order = [p["university"]["name"] for p in anonymous.json()]
    assert anon_order[0] == "Alpha Institute"
    assert all(p["university"]["is_favorite"] is False for p in anonymous.json())

    await client.put(f"/api/v1/universities/{universities[2].id}/favorite", headers=auth_headers)

    signed_in = await client.get(
        "/api/v1/universities/programs", params=params, headers=auth_headers
    )
    programs = signed_in.json()
    assert programs[0]["university"]["name"] == "Gamma College"
    assert programs[0]["university"]["is_favorite"] is True
    # Everything below the starred one keeps its previous relative order.
    assert [p["university"]["name"] for p in programs[1:]] == anon_order[:-1]

    # The public, token-less response is unchanged — this endpoint predates
    # favourites and must keep working identically without one.
    still_anonymous = await client.get("/api/v1/universities/programs", params=params)
    assert [p["university"]["name"] for p in still_anonymous.json()] == anon_order
