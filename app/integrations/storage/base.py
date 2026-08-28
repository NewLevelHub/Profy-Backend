from typing import Protocol


class StorageBackend(Protocol):
    """Minimal contract the photo-import pipeline needs. No delete/list —
    add only when something actually needs them."""

    async def put_object(self, key: str, data: bytes, *, content_type: str) -> None: ...

    async def object_exists(self, key: str) -> bool: ...
