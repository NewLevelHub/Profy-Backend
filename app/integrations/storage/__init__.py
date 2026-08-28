from app.config import Settings
from app.integrations.storage.base import StorageBackend
from app.integrations.storage.filesystem import FilesystemStorageBackend


def build_storage_backend(settings: Settings) -> StorageBackend:
    """Single place that knows how to construct a backend from config —
    callers never hand-build one themselves.

    Defaults to the filesystem backend (photos on disk, served by nginx, no
    extra service). STORAGE_BACKEND=s3 switches to the S3-compatible client;
    boto3 is imported only on that path, so an fs-only deployment doesn't
    need it installed.
    """
    if settings.STORAGE_BACKEND == "s3":
        from app.integrations.storage.s3 import S3StorageBackend

        return S3StorageBackend(
            endpoint_url=settings.STORAGE_ENDPOINT_URL,
            region=settings.STORAGE_REGION,
            access_key=settings.STORAGE_ACCESS_KEY,
            secret_key=settings.STORAGE_SECRET_KEY,
            bucket=settings.STORAGE_BUCKET,
            use_path_style=settings.STORAGE_USE_PATH_STYLE,
        )
    return FilesystemStorageBackend(root=settings.STORAGE_FS_ROOT)
