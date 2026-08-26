"""Pure, no I/O — build_public_url is the entire storage/CDN vendor-swap
seam (see app/integrations/storage/urls.py), so it earns table-driven cases
independent of any storage backend."""
import pytest

from app.config import settings
from app.integrations.storage.urls import build_public_url


@pytest.mark.parametrize(
    ("base_url", "storage_key", "expected"),
    [
        ("http://localhost/media", "universities/abc/1.webp", "http://localhost/media/universities/abc/1.webp"),
        ("http://localhost/media/", "universities/abc/1.webp", "http://localhost/media/universities/abc/1.webp"),
        ("http://localhost/media", "/universities/abc/1.webp", "http://localhost/media/universities/abc/1.webp"),
        ("http://localhost/media/", "/universities/abc/1.webp", "http://localhost/media/universities/abc/1.webp"),
        ("https://cdn.example.com", "x/y.png", "https://cdn.example.com/x/y.png"),
    ],
)
def test_build_public_url(monkeypatch: pytest.MonkeyPatch, base_url: str, storage_key: str, expected: str) -> None:
    monkeypatch.setattr(settings, "STORAGE_PUBLIC_BASE_URL", base_url)
    assert build_public_url(storage_key) == expected
