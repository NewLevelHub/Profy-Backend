from fastapi import APIRouter

from app.routers.artifacts import router as artifacts_router
from app.routers.assessment import router as assessment_router
from app.routers.auth import router as auth_router
from app.routers.directions import router as directions_router
from app.routers.profile import router as profile_router
from app.routers.questions import router as questions_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/api/v1/auth")
api_router.include_router(profile_router, prefix="/api/v1/profile")
api_router.include_router(artifacts_router, prefix="/api/v1/profile/artifacts")
api_router.include_router(assessment_router, prefix="/api/v1/assessment")
api_router.include_router(questions_router, prefix="/api/v1/assessment")
api_router.include_router(directions_router, prefix="/api/v1/directions")
