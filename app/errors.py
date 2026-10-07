"""Application error type carrying a stable machine ``error_code`` (KZ-309).

Contract §7: the backend keeps the human-readable Russian ``detail`` for
backward compatibility and *adds* a stable ``error_code`` next to it in the
error body. The frontend maps ``error_code`` → localized copy (KZ-203); it must
never parse the Russian ``detail``.

Usage — replace a user-facing Russian ``HTTPException`` with::

    raise AppError(
        status_code=status.HTTP_400_BAD_REQUEST,
        error_code="goal_change_limit_reached",
        detail="Достигнут лимит смены целей (максимум 3 раза)",
    )

The response body becomes ``{"detail": "<ru text>", "error_code": "<code>"}``.
Plain ``HTTPException`` still renders as ``{"detail": ...}`` unchanged — only
error strings that need client-side localization are migrated to ``AppError``.
"""

from __future__ import annotations

from fastapi import HTTPException


class AppError(HTTPException):
    """``HTTPException`` plus a machine-readable ``error_code`` (see module doc)."""

    def __init__(
        self,
        *,
        status_code: int,
        error_code: str,
        detail: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.error_code = error_code
