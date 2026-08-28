import asyncio
from pathlib import Path


class FilesystemStorageBackend:
    """Writes photos into a local directory that nginx serves directly at
    STORAGE_PUBLIC_BASE_URL — no object-storage server in the loop. This is
    the default backend: university photos are a fixed, rarely-changing set
    (imported by the offline scripts in scripts/), so a plain directory plus
    an nginx `alias` covers the whole read path with zero extra services.

    The DB only ever stores the relative storage_key, byte-for-byte identical
    to what S3StorageBackend produces, so switching backends never touches
    data. S3StorageBackend stays available for deployments that genuinely
    need an object store (browser uploads, multi-node serving) — select it
    with STORAGE_BACKEND=s3.

    Same host folder is mounted into the api container read-write (so the
    import scripts can write) and into nginx read-only (so it can serve);
    see docker-compose.yml.
    """

    def __init__(self, *, root: str) -> None:
        self._root = Path(root)

    async def put_object(self, key: str, data: bytes, *, content_type: str) -> None:
        # content_type is part of the StorageBackend contract but irrelevant
        # on disk: nginx derives the response Content-Type from the file
        # extension (mime.types), and every storage_key already carries one.
        path = self._root / key
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def object_exists(self, key: str) -> bool:
        return await asyncio.to_thread((self._root / key).is_file)
