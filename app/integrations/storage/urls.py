from app.config import settings


def build_public_url(storage_key: str) -> str:
    """The entire storage/CDN vendor-swap seam: only STORAGE_PUBLIC_BASE_URL
    changes across environments, and the DB only ever stores relative
    storage_keys — so swapping vendors later never requires a data
    migration."""
    return f"{settings.STORAGE_PUBLIC_BASE_URL.rstrip('/')}/{storage_key.lstrip('/')}"
