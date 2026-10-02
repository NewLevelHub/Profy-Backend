from pydantic import BaseModel, Field, model_validator

from app.i18n.catalog import key as i18n_key
from app.models.artifact import ArtifactType

# Mirrors the frontend's ARTIFACT_VALUE_MAX_LENGTH / ARTIFACT_GOAL_MAX_LENGTH
# (src/shared/config/constants.ts). A chip value is a short label ("Программист",
# a hobby, a country); `goal`/`dream` are the free-text "мечты" answer.
ARTIFACT_VALUE_MAX_LENGTH = 60
ARTIFACT_FREE_TEXT_MAX_LENGTH = 500

_FREE_TEXT_TYPES = frozenset({ArtifactType.goal, ArtifactType.dream})


def artifact_value_max_length(artifact_type: ArtifactType) -> int:
    if artifact_type in _FREE_TEXT_TYPES:
        return ARTIFACT_FREE_TEXT_MAX_LENGTH
    return ARTIFACT_VALUE_MAX_LENGTH


class ArtifactItem(BaseModel):
    type: ArtifactType
    value: str = Field(..., min_length=1)


class ArtifactInput(ArtifactItem):
    """Request shape: ArtifactItem plus the per-type length cap. Responses keep
    the plain ArtifactItem, so a stored value is always readable back."""

    model_config = {"str_strip_whitespace": True}

    @model_validator(mode="after")
    def _value_fits_type(self) -> "ArtifactInput":
        max_length = artifact_value_max_length(self.type)
        if len(self.value) > max_length:
            raise ValueError(
                i18n_key("api_errors", "custom_value_too_long").format(max_length=max_length)
            )
        return self


class ArtifactsBulkRequest(BaseModel):
    items: list[ArtifactInput]


class ArtifactsResponse(BaseModel):
    items: list[ArtifactItem]
