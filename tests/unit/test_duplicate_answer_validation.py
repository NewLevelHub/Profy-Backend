import uuid

import pytest
from pydantic import ValidationError

from app.schemas.motivation import SubmitMotivationRequest
from app.schemas.question_pair import SubmitPairAnswersRequest
from app.schemas.response import SubmitAnswersRequest


_DUPLICATE_QUESTION_ID = str(uuid.uuid4())


@pytest.mark.parametrize(
    ("schema", "payload", "error_code"),
    [
        (
            SubmitAnswersRequest,
            {
                "answers": [
                    {"question_id": str(uuid.uuid4()), "value": 2},
                    {"question_id": _DUPLICATE_QUESTION_ID, "value": 2},
                    {"question_id": _DUPLICATE_QUESTION_ID, "value": 5},
                ]
            },
            "duplicate_question_ids",
        ),
        (
            SubmitPairAnswersRequest,
            {
                "answers": [
                    {"pair_index": 7, "picked_question_id": str(uuid.uuid4())},
                    {"pair_index": 7, "picked_question_id": str(uuid.uuid4())},
                ]
            },
            "duplicate_pair_indexes",
        ),
        (
            SubmitMotivationRequest,
            {
                "answers": [
                    {
                        "triplet_index": 3,
                        "most_statement_id": str(uuid.uuid4()),
                        "least_statement_id": str(uuid.uuid4()),
                    },
                    {
                        "triplet_index": 3,
                        "most_statement_id": str(uuid.uuid4()),
                        "least_statement_id": str(uuid.uuid4()),
                    },
                ]
            },
            "duplicate_triplet_indexes",
        ),
    ],
)
def test_submit_schemas_reject_duplicate_identifiers(
    schema, payload: dict, error_code: str
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        schema.model_validate(payload)

    [error] = exc_info.value.errors()
    assert error["loc"] == ("answers",)
    assert error["type"] == error_code
