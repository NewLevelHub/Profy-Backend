from pydantic import BaseModel, Field

from app.models.artifact import ArtifactType


class ArtifactItem(BaseModel):
    type: ArtifactType
    value: str = Field(..., min_length=1)


class ArtifactsBulkRequest(BaseModel):
    items: list[ArtifactItem]


class ArtifactsResponse(BaseModel):
    items: list[ArtifactItem]
