import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.database import engine
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
