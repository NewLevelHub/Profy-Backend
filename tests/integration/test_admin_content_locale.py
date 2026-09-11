"""Admin content lists carry and filter by `locale`.

KZ-301 turned one logical content unit into one row per locale, which doubled
every admin content list without telling the admin which copy each row is: the
`ru` and the `kk` version of the same question come back to back, structurally
identical, and an admin editing "the" question cannot see which language they
are about to change. KZ-210 originally left the panel `ru`-only, so nobody
noticed; that decision was reversed on PR review.

What is pinned here: every list item reports its `locale`, the filter narrows
to exactly one locale, `total` reflects the filter (a `total` counting the
unfiltered set would paginate into empty pages), and the endpoint rejects a
locale outside `KNOWN_LOCALES` rather than silently returning everything.

Real transactional Postgres session (rolled back), seeded content — the rows
read here are the ones the panel actually shows.
"""

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services import admin_content_service, auth_service

# (label, service callable) — the five content lists that gained the filter.
_LISTS = [
    ("questions", admin_content_service.list_questions),
    ("question_pairs", admin_content_service.list_question_pairs),
    ("motivation_statements", admin_content_service.list_motivation_statements),
    ("motivation_pairs", admin_content_service.list_motivation_pairs),
    ("directions", admin_content_service.list_directions),
]

# Endpoint path per list, for the router-level checks.
_PATHS = [
    "/api/v1/admin/questions",
    "/api/v1/admin/question-pairs",
    "/api/v1/admin/motivation-statements",
    "/api/v1/admin/motivation-pairs",
    "/api/v1/admin/directions",
]


@pytest.fixture
async def admin_headers(db_session: AsyncSession) -> dict[str, str]:
    admin = User(
        email=f"admin-{id(db_session)}@example.test",
        hashed_password=auth_service.hash_password("Testpass123!"),
        is_active=True,
        is_verified=True,
        is_admin=True,
    )
    db_session.add(admin)
    await db_session.flush()
    return {"Authorization": f"Bearer {auth_service.create_jwt_token(admin.id)}"}


@pytest.mark.parametrize("label,list_fn", _LISTS, ids=[label for label, _ in _LISTS])
async def test_every_item_reports_its_locale(db_session: AsyncSession, label, list_fn) -> None:
    """Without this field the two copies of a row are indistinguishable in the
    table — the exact defect reported on the PR."""
    page = await list_fn(db_session, limit=100)
    assert page.items, f"{label}: no seeded rows to check"
    assert all(item.locale for item in page.items)


@pytest.mark.parametrize("label,list_fn", _LISTS, ids=[label for label, _ in _LISTS])
@pytest.mark.parametrize("locale", ["ru", "kk"])
async def test_filter_returns_only_that_locale(db_session: AsyncSession, label, list_fn, locale) -> None:
    page = await list_fn(db_session, locale=locale, limit=100)
    assert page.items, f"{label}: no {locale} rows"
    assert {item.locale for item in page.items} == {locale}


@pytest.mark.parametrize("label,list_fn", _LISTS, ids=[label for label, _ in _LISTS])
async def test_total_reflects_the_filter(db_session: AsyncSession, label, list_fn) -> None:
    """`total` drives the pager. Counting the unfiltered set while returning a
    filtered page would render pages that come back empty."""
    unfiltered = await list_fn(db_session, limit=1)
    ru = await list_fn(db_session, locale="ru", limit=1)
    kk = await list_fn(db_session, locale="kk", limit=1)

    assert ru.total < unfiltered.total
    assert kk.total < unfiltered.total
    assert ru.total + kk.total == unfiltered.total, f"{label}: a row belongs to neither locale"


@pytest.mark.parametrize("path", _PATHS)
async def test_endpoint_accepts_a_known_locale(
    client: httpx.AsyncClient, admin_headers: dict[str, str], path: str
) -> None:
    response = await client.get(path, params={"locale": "kk"}, headers=admin_headers)
    assert response.status_code == 200
    items = response.json()["items"]
    assert items and {item["locale"] for item in items} == {"kk"}


@pytest.mark.parametrize("bad", ["en", "KK", "ru,kk", ""])
async def test_endpoint_rejects_an_unknown_locale(
    client: httpx.AsyncClient, admin_headers: dict[str, str], bad: str
) -> None:
    """Rejecting is the point: a typo that quietly fell through to "no filter"
    would show both locales while the toolbar claims one."""
    response = await client.get(
        "/api/v1/admin/questions", params={"locale": bad}, headers=admin_headers
    )
    assert response.status_code == 422
