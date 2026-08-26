from app.config import Settings
from app.integrations.storage.base import StorageBackend
from app.integrations.storage.s3 import S3StorageBackend


def build_storage_backend(settings: Settings) -> StorageBackend:
    """Single place that knows how to construct a backend from config —
    callers never hand-build a boto3 client themselves."""
    return S3StorageBackend(
        endpoint_url=settings.STORAGE_ENDPOINT_URL,
        region=settings.STORAGE_REGION,
        access_key=settings.STORAGE_ACCESS_KEY,
        secret_key=settings.STORAGE_SECRET_KEY,
        bucket=settings.STORAGE_BUCKET,
        use_path_style=settings.STORAGE_USE_PATH_STYLE,
    )
