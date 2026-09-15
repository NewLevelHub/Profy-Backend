"""OpenAPI-shape checks for /result — the generated schema must actually
reflect the discriminated MI/RIASEC contract (frontend-result-api-contract.md
§4), not just "the Python types happen to validate correctly". Pure schema
generation (`app.openapi()`), no DB/app startup/lifespan involved.
"""
from app.main import app


_STUDENT_RESPONSE_NAMES = {"MiResultResponse", "RiasecResultResponse"}


def _result_generate_response_schema() -> dict:
    schema = app.openapi()
    post = schema["paths"]["/api/v1/result/generate"]["post"]
    return post["responses"]["200"]["content"]["application/json"]["schema"]


def _components(schema_key: str) -> dict:
    return app.openapi()["components"]["schemas"][schema_key]


def _response_branches() -> list[dict]:
    """/generate returns either the report or the pending-review envelope
    (PRO-337) — an anyOf of the two, each branch resolved through $ref."""
    response_schema = _result_generate_response_schema()
    branches = []
    for branch in response_schema.get("anyOf", [response_schema]):
        if "$ref" in branch:
            branch = {**_components(branch["$ref"].rsplit("/", 1)[-1]), "__ref__": branch["$ref"]}
        branches.append(branch)
    return branches


def test_result_generate_response_is_a_discriminated_oneof():
    # A $ref'd oneOf (pydantic wraps discriminated unions this way) or an
    # inline oneOf — either is fine, but it must not have collapsed into a
    # single flat object schema (that would mean the discriminator was lost).
    discriminated = [b for b in _response_branches() if "discriminator" in b]
    assert len(discriminated) == 1
    assert "oneOf" in discriminated[0]
    assert discriminated[0]["discriminator"]["propertyName"] == "interest_instrument"


def test_result_generate_response_allows_pending_review_envelope():
    refs = {b.get("__ref__", "") for b in _response_branches()}
    assert any(ref.endswith("/ResultPendingReviewResponse") for ref in refs)


def test_mi_and_riasec_schemas_are_both_registered_in_components():
    schema = app.openapi()
    component_names = set(schema["components"]["schemas"])
    assert _STUDENT_RESPONSE_NAMES <= component_names


def test_disclaimer_field_is_present_on_both_branches():
    schema = app.openapi()
    component_names = [n for n in schema["components"]["schemas"] if n in _STUDENT_RESPONSE_NAMES]
    assert set(component_names) == _STUDENT_RESPONSE_NAMES
    for name in component_names:
        properties = schema["components"]["schemas"][name]["properties"]
        assert "disclaimer" in properties


def test_student_response_schemas_never_expose_admin_only_fields():
    schema = app.openapi()
    admin_only = {"profile", "code", "meta", "big_five", "match_score"}
    for name in _STUDENT_RESPONSE_NAMES:
        properties = set(schema["components"]["schemas"][name].get("properties", {}))
        assert properties & admin_only == set(), f"{name} leaks admin-only fields: {properties & admin_only}"
