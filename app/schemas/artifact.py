from pydantic import BaseModel

from app.models.artifact import ArtifactType


class ArtifactItem(BaseModel):
    type: ArtifactType
    value: str


class ArtifactsBulkRequest(BaseModel):
    items: list[ArtifactItem]


class ArtifactsResponse(BaseModel):
    items: list[ArtifactItem]
