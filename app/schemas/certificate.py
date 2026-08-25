from pydantic import BaseModel, model_validator

from app.models.certificate import CertificateType

# Valid score ranges per exam. Mirrors the frontend's CERTIFICATE_CONFIG
# (certificateConfig.ts) so an out-of-range score is rejected here with a
# clean 422 rather than reaching the DB layer.
SCORE_RANGES: dict[CertificateType, tuple[float, float]] = {
    CertificateType.ielts: (0.0, 9.0),
    CertificateType.toefl: (0.0, 120.0),
    CertificateType.sat: (400.0, 1600.0),
    CertificateType.unt: (0.0, 140.0),
}


class CertificateItem(BaseModel):
    type: CertificateType
    score: float

    @model_validator(mode="after")
    def _validate_score_range(self) -> "CertificateItem":
        low, high = SCORE_RANGES[self.type]
        if not (low <= self.score <= high):
            raise ValueError(f"score for {self.type.value} must be between {low} and {high}")
        return self


class CertificatesBulkRequest(BaseModel):
    items: list[CertificateItem]


class CertificatesResponse(BaseModel):
    items: list[CertificateItem]
