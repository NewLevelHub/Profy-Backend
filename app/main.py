import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.errors import AppError
from app.i18n import _current_locale, normalize_locale
from app.i18n.catalog import key as i18n_key
from app.routers import api_router
from app.services.admin_listing import AdminSortFieldError
from app.services.scheduling.reminders import run_week_reminders_loop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_VALIDATION_MESSAGE_KEYS = {
    "missing": "field_required",
    "string_type": "string_required",
    # Size ceilings (app/schemas/validation.py); `{max_length}` comes from the
    # error's own `ctx`. "too_long" is pydantic's type for a list or a map.
    "string_too_long": "value_too_long",
    "too_long": "list_too_long",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("Database connected")
    reminders = (
        asyncio.create_task(run_week_reminders_loop()) if settings.WEEK_REMINDERS_ENABLED else None
    )
    yield
    if reminders is not None:
        reminders.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reminders
    await engine.dispose()


def docs_routes() -> dict[str, str | None]:
    """Swagger UI and the OpenAPI schema are the full map of the API, admin
    routes included — served only where the stack allows it (not production,
    see `API_DOCS_ENABLED`). ReDoc is never served: nothing links to it."""
    enabled = settings.API_DOCS_ENABLED
    return {
        "docs_url": "/docs" if enabled else None,
        "redoc_url": None,
        "openapi_url": "/openapi.json" if enabled else None,
    }


app = FastAPI(
    title="Profi API",
    version="0.1.0",
    lifespan=lifespan,
    **docs_routes(),
)

# Only the configured origins may read responses cross-origin. Credentials
# mode stays off: the session is a Bearer token in the Authorization header,
# never a cookie, so no browser-attached credential has to cross origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Accept-Language"],
)


@app.middleware("http")
async def locale_middleware(request: Request, call_next):
    """Seed the request locale from ``Accept-Language`` before any route runs.

    ``get_current_user`` refines this from ``users.locale`` for authenticated
    requests (users.locale wins over the header) — see app/dependencies.py.
    Services read the value via ``app.i18n.get_locale()``.
    """
    token = _current_locale.set(
        normalize_locale(request.headers.get("accept-language"))
    )
    try:
        return await call_next(request)
    finally:
        _current_locale.reset(token)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Render :class:`AppError` as ``{"detail": <ru text>, "error_code": <code>}``
    (KZ-309 / contract §7) — ``detail`` stays byte-identical to the pre-KZ-309
    body, ``error_code`` is added for client-side localization."""
    return JSONResponse(
        status_code=exc.status_code,
        content={**exc.extra, "detail": exc.detail, "error_code": exc.error_code},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Localize the built-in validation errors used by request schemas.

    Only ``msg`` changes: ``type`` and ``loc`` remain stable. Domain rules use
    ``PydanticCustomError`` with catalog text at the validation site and
    therefore are intentionally left untouched here.

    ``input`` — the rejected value itself — is dropped from every error: for
    a too-short password, a wrong code or an invitation token it is the
    secret, and a 422 body ends up in browser consoles and error trackers.
    ``loc`` already says which field was wrong.
    """
    errors = []
    for error in exc.errors():
        error = {name: value for name, value in error.items() if name != "input"}
        if message_key := _VALIDATION_MESSAGE_KEYS.get(error.get("type")):
            error["msg"] = i18n_key("api_errors", message_key).format(**error.get("ctx", {}))
        errors.append(error)
    return await request_validation_exception_handler(
        request, RequestValidationError(errors, body=exc.body)
    )


@app.exception_handler(AdminSortFieldError)
async def _admin_sort_field_error_handler(
    request: Request, exc: AdminSortFieldError
) -> JSONResponse:
    """`?sort=` naming a field an endpoint cannot sort by is a bad request,
    handled once here instead of a try/except around all seven admin list
    endpoints. The allowed set is returned with the error so the caller can
    see what this particular list supports."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": str(exc), "allowed_sort_fields": exc.allowed},
    )


app.include_router(api_router)
