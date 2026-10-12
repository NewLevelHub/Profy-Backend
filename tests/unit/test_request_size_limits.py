"""Every field a client can send has an upper size bound (SEC-14).

Without one a single request overflows a varchar column (a 500 where a 422
belongs), bloats a JSONB column or hands the database an `IN (...)` of any
length. The first test walks the whole API, so a request field added later
without a limit fails here; the rest pin limits that are easy to get wrong.
"""

import uuid
from decimal import Decimal

import httpx
import pytest
from pydantic import ValidationError

from app.i18n.catalog import api_errors
from app.main import app
from app.schemas.admin_university import AdminProgramUpdateRequest, AdminUniversityUpdateRequest
from app.schemas.artifact import ArtifactInput
from app.schemas.auth import PASSWORD_MAX_LENGTH, LoginRequest, RegisterRequest
from app.schemas.belbin import SaveBelbinProgressRequest
from app.schemas.profile import (
    LANGUAGE_MAX_LENGTH,
    PLACE_MAX_LENGTH,
    SUBJECT_MAX_LENGTH,
    SUBJECTS_MAX_ITEMS,
    ProfileCreateRequest,
    ProfileUpdateRequest,
)
from app.schemas.psychologist import PsychologistNoteCreate
from app.schemas.response import ANSWERS_MAX_ITEMS, SubmitAnswersRequest
from app.schemas.validation import ANSWER_MAP_MAX_ITEMS, LONG_TEXT_MAX_LENGTH

# Open JSON by design: several importers and an admin editor write whole
# documents into these, so there is no per-key shape to bound. Their ceiling
# is the request-size limit of nginx (`client_max_body_size`, checked in
# tests/deployment). Adding an entry here needs the same kind of reason.
OPEN_BY_DESIGN = {
    "AdminContentOverrideRequest.content_ru",
    "AdminContentOverrideRequest.content_kk",
    "AdminProgramUpdateRequest.requirements",
    "AdminProgramUpdateRequest.deadlines",
    "UpdateAsturDraftRequest.document",
    # A Decimal may arrive as a string; its value is bounded (gt / lt).
    "AdminProgramUpdateRequest.cost_per_year",
}

_SELF_LIMITING_FORMATS = {"uuid", "date-time", "date", "email"}


def _unbounded_request_fields() -> set[str]:
    schema = app.openapi()
    components = schema["components"]["schemas"]
    found: set[str] = set()

    def walk(node: dict, path: str, seen: tuple[str, ...] = ()) -> None:
        ref = node.get("$ref")
        if ref:
            if ref in seen:
                return
            seen += (ref,)
            node = components[ref.rsplit("/", 1)[1]]
        for key in ("anyOf", "oneOf", "allOf"):
            for option in node.get(key, []):
                walk(option, path, seen)
        kind = node.get("type")
        if kind == "string":
            bounded = "maxLength" in node or "enum" in node or "const" in node
            if not bounded and node.get("format") not in _SELF_LIMITING_FORMATS:
                found.add(path)
        elif kind == "array":
            if "maxItems" not in node:
                found.add(path)
            walk(node.get("items", {}), f"{path}[]", seen)
        elif kind == "object":
            properties = node.get("properties")
            values = node.get("additionalProperties")
            if properties is None:
                # A map: bounded when its size is capped and its values are typed.
                if "maxProperties" not in node or not isinstance(values, dict) or not values:
                    found.add(path)
            for name, child in (properties or {}).items():
                walk(child, f"{path}.{name}", seen)
            if isinstance(values, dict) and values:
                walk(values, f"{path}.*", seen)

    for methods in schema["paths"].values():
        for operation in methods.values():
            for spec in operation.get("requestBody", {}).get("content", {}).values():
                body = spec.get("schema", {})
                walk(body, body.get("$ref", "body").rsplit("/", 1)[-1])
    return found


def test_every_request_field_has_an_upper_bound() -> None:
    unbounded = _unbounded_request_fields()

    assert unbounded - OPEN_BY_DESIGN == set(), "request fields with no size limit"
    assert OPEN_BY_DESIGN - unbounded == set(), "no longer open — remove from OPEN_BY_DESIGN"


# --- what a student or an anonymous visitor sends -----------------------------


def _profile(**overrides) -> dict:
    body = dict(name="Анна", age=16, grade=10, city="Алматы", country="Казахстан", language="ru")
    body.update(overrides)
    return body


@pytest.mark.parametrize(
    "overrides",
    [
        {"city": "я" * (PLACE_MAX_LENGTH + 1)},
        {"country": "я" * (PLACE_MAX_LENGTH + 1)},
        # `profiles.language` is varchar(50): one more character used to be a 500.
        {"language": "x" * (LANGUAGE_MAX_LENGTH + 1)},
        {"subjects_liked": ["Химия"] * (SUBJECTS_MAX_ITEMS + 1)},
        {"subjects_hard": ["я" * (SUBJECT_MAX_LENGTH + 1)]},
        {"artifacts": [{"type": "hobby", "value": "Шахматы"}] * 101},
        {"certificates": [{"type": "ielts", "score": 7.0}] * 21},
    ],
)
def test_oversized_profile_values_are_rejected(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        ProfileCreateRequest(**_profile(**overrides))
    with pytest.raises(ValidationError):
        ProfileUpdateRequest(**overrides)


def test_values_at_the_limit_and_the_forms_real_payload_still_pass() -> None:
    at_the_limit = ProfileCreateRequest(
        **_profile(
            city="я" * PLACE_MAX_LENGTH,
            language="x" * LANGUAGE_MAX_LENGTH,
            subjects_liked=["я" * SUBJECT_MAX_LENGTH] * SUBJECTS_MAX_ITEMS,
        )
    )
    assert len(at_the_limit.subjects_liked) == SUBJECTS_MAX_ITEMS
    # The onboarding form sends an empty language: a ceiling is not a floor.
    assert ProfileCreateRequest(**_profile(language="")).language == ""


def test_artifact_keeps_its_tighter_per_type_cap() -> None:
    ArtifactInput(type="goal", value="я" * 500)
    with pytest.raises(ValidationError):
        ArtifactInput(type="goal", value="я" * 501)
    with pytest.raises(ValidationError, match="60"):
        ArtifactInput(type="hobby", value="я" * 61)


def test_password_has_a_ceiling_on_every_path_that_hashes_it() -> None:
    too_long = "a1" + "x" * (PASSWORD_MAX_LENGTH - 1)
    with pytest.raises(ValidationError):
        RegisterRequest(email="a@example.com", password=too_long)
    with pytest.raises(ValidationError):
        LoginRequest(email="a@example.com", password=too_long)
    assert RegisterRequest(email="a@example.com", password="a1" + "x" * (PASSWORD_MAX_LENGTH - 2))


def test_answer_batch_is_capped_above_the_whole_battery() -> None:
    def answers(count: int) -> list[dict]:
        return [{"question_id": str(uuid.uuid4()), "value": 3} for _ in range(count)]

    # Today's battery is 485 questions — a whole run in one request must fit.
    assert len(SubmitAnswersRequest(answers=answers(485)).answers) == 485
    with pytest.raises(ValidationError):
        SubmitAnswersRequest(answers=answers(ANSWERS_MAX_ITEMS + 1))


def test_answer_maps_are_capped() -> None:
    assert SaveBelbinProgressRequest(allocation={f"item{i}": 1 for i in range(10)})
    with pytest.raises(ValidationError):
        SaveBelbinProgressRequest(allocation={f"item{i}": 0 for i in range(ANSWER_MAP_MAX_ITEMS + 1)})
    with pytest.raises(ValidationError):
        SaveBelbinProgressRequest(allocation={"k" * 65: 1})


# --- what staff send -------------------------------------------------------------


def test_note_has_a_ceiling_far_above_a_real_note() -> None:
    assert PsychologistNoteCreate(content="я" * LONG_TEXT_MAX_LENGTH)
    with pytest.raises(ValidationError):
        PsychologistNoteCreate(content="я" * (LONG_TEXT_MAX_LENGTH + 1))


@pytest.mark.parametrize(
    ("field", "column_width"),
    [("name", 255), ("short_name", 100), ("city", 100), ("country", 100), ("ranking_label", 100), ("uniranks_note", 50)],
)
def test_university_fields_stop_at_the_width_of_their_column(field: str, column_width: int) -> None:
    assert AdminUniversityUpdateRequest(**{field: "я" * column_width})
    with pytest.raises(ValidationError):
        AdminUniversityUpdateRequest(**{field: "я" * (column_width + 1)})


def test_program_cost_fits_its_numeric_column_without_changing_rounding() -> None:
    # numeric(12, 2): extra decimals are the column's business, as before.
    assert AdminProgramUpdateRequest(cost_per_year="1234.567").cost_per_year == Decimal("1234.567")
    assert AdminProgramUpdateRequest(cost_per_year=9_999_999_999).cost_per_year == Decimal(9_999_999_999)
    with pytest.raises(ValidationError):
        AdminProgramUpdateRequest(cost_per_year=10**10)


# --- how the refusal reads ----------------------------------------------------------


async def _post(path: str, body: dict, *, locale: str) -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(path, json=body, headers={"Accept-Language": locale})


@pytest.mark.parametrize("locale", ["ru", "kk"])
async def test_too_long_a_value_is_refused_in_the_readers_language(locale: str) -> None:
    catalog = {"ru": api_errors.RU, "kk": api_errors.KK}[locale]
    response = await _post(
        "/api/v1/auth/register",
        {"email": "a@example.com", "password": "a1" + "x" * PASSWORD_MAX_LENGTH},
        locale=locale,
    )

    assert response.status_code == 422
    (error,) = response.json()["detail"]
    assert error["type"] == "string_too_long"
    assert error["loc"] == ["body", "password"]
    assert error["msg"] == catalog["value_too_long"].format(max_length=PASSWORD_MAX_LENGTH)
    assert str(PASSWORD_MAX_LENGTH) in error["msg"]


async def test_too_many_items_are_refused_in_the_readers_language(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.put(
        "/api/v1/profile",
        headers=auth_headers,
        json={"subjects_liked": ["Химия"] * (SUBJECTS_MAX_ITEMS + 1)},
    )

    assert response.status_code == 422
    (error,) = response.json()["detail"]
    assert error["type"] == "too_long"
    assert error["loc"] == ["body", "subjects_liked"]
    assert error["msg"] == api_errors.RU["list_too_long"].format(max_length=SUBJECTS_MAX_ITEMS)


async def test_a_value_wider_than_its_column_is_a_422_not_a_500(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    """`profiles.language` is varchar(50). Before the limit this request went
    all the way to the INSERT and failed there."""
    response = await client.post(
        "/api/v1/profile",
        headers=auth_headers,
        json=_profile(language="x" * (LANGUAGE_MAX_LENGTH + 1)),
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "language"]
