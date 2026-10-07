import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.database import engine
from app.errors import AppError
from app.i18n import _current_locale, normalize_locale
from app.routers import api_router
from app.services.admin_listing import AdminSortFieldError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("Database connected")
    yield
    await engine.dispose()


app = FastAPI(
    title="Profi API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
        content={"detail": exc.detail, "error_code": exc.error_code},
        headers=exc.headers,
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
