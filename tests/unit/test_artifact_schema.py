"""Length caps on artifact values sent from onboarding (custom «+ своё» chips)."""

import pytest
from pydantic import ValidationError

from app.models.artifact import ArtifactType
from app.schemas.artifact import (
    ARTIFACT_FREE_TEXT_MAX_LENGTH,
    ARTIFACT_VALUE_MAX_LENGTH,
    ArtifactInput,
    ArtifactItem,
)


def test_chip_value_at_limit_is_accepted() -> None:
    item = ArtifactInput(type=ArtifactType.profession, value="а" * ARTIFACT_VALUE_MAX_LENGTH)
    assert len(item.value) == ARTIFACT_VALUE_MAX_LENGTH


def test_chip_value_over_limit_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ArtifactInput(type=ArtifactType.profession, value="а" * (ARTIFACT_VALUE_MAX_LENGTH + 1))


def test_goal_gets_free_text_limit() -> None:
    ArtifactInput(type=ArtifactType.goal, value="а" * ARTIFACT_FREE_TEXT_MAX_LENGTH)
    with pytest.raises(ValidationError):
        ArtifactInput(type=ArtifactType.goal, value="а" * (ARTIFACT_FREE_TEXT_MAX_LENGTH + 1))


def test_value_is_stripped_before_length_and_emptiness_checks() -> None:
    padded = "  " + "а" * ARTIFACT_VALUE_MAX_LENGTH + "  "
    assert ArtifactInput(type=ArtifactType.hobby, value=padded).value == "а" * ARTIFACT_VALUE_MAX_LENGTH
    with pytest.raises(ValidationError):
        ArtifactInput(type=ArtifactType.hobby, value="   ")


def test_response_shape_does_not_cap_stored_values() -> None:
    long_value = "а" * (ARTIFACT_VALUE_MAX_LENGTH * 10)
    assert ArtifactItem(type=ArtifactType.profession, value=long_value).value == long_value


def test_custom_subject_over_limit_is_rejected() -> None:
    from app.schemas.profile import SUBJECT_MAX_LENGTH, ProfileUpdateRequest

    ProfileUpdateRequest(subjects_liked=["а" * SUBJECT_MAX_LENGTH])
    with pytest.raises(ValidationError):
        ProfileUpdateRequest(subjects_hard=["а" * (SUBJECT_MAX_LENGTH + 1)])
