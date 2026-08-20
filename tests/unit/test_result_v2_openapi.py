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


def test_result_generate_response_is_a_discriminated_oneof():
    response_schema = _result_generate_response_schema()
    # A $ref'd oneOf (pydantic wraps discriminated unions this way) or an
    # inline oneOf — either is fine, but it must not have collapsed into a
    # single flat object schema (that would mean the discriminator was lost).
    if "$ref" in response_schema:
        ref_name = response_schema["$ref"].rsplit("/", 1)[-1]
        response_schema = _components(ref_name)
    assert "oneOf" in response_schema
    assert "discriminator" in response_schema
    assert response_schema["discriminator"]["propertyName"] == "interest_instrument"


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
