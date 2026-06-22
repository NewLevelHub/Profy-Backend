from fastapi import APIRouter

from app.routers.auth import router as auth_router
from app.routers.profile import router as profile_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/api/v1/auth")
api_router.include_router(profile_router, prefix="/api/v1/profile")
