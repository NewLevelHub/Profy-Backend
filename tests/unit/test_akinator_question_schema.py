import pytest
from pydantic import ValidationError

from app.schemas.akinator_question import AkinatorQuestionCreate


def _payload(axis_weights: dict[str, int]) -> dict:
    return {
        "kind": "direct",
        "depth": 0,
        "text": "Что тебе интереснее всего?",
        "options": [{"text": "быть среди людей, общаться, помогать", "axis_weights": axis_weights}],
    }


def test_valid_axis_weights_pass():
    question = AkinatorQuestionCreate.model_validate(_payload({"People": 2, "Care": 1}))
    assert question.options[0].axis_weights == {"People": 2, "Care": 1}


def test_typo_axis_code_is_rejected():
    with pytest.raises(ValidationError):
        AkinatorQuestionCreate.model_validate(_payload({"Peple": 2}))


def test_legacy_prefixed_axis_code_is_rejected():
    with pytest.raises(ValidationError):
        AkinatorQuestionCreate.model_validate(_payload({"A_people": 2}))
