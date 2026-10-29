from typing import Any

from app.errors import AppError
from app.i18n.catalog import key as i18n_key


def crm_error(status_code: int, error_code: str, **extra: Any) -> AppError:
    return AppError(
        status_code=status_code,
        error_code=error_code,
        detail=i18n_key("api_errors", error_code),
        extra=extra or None,
    )
