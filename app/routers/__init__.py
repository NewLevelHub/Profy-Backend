from fastapi import APIRouter

from app.routers.admin import router as admin_router
from app.routers.akinator import router as akinator_router
from app.routers.artifacts import router as artifacts_router
from app.routers.assessment import router as assessment_router
from app.routers.auth import router as auth_router
from app.routers.directions import router as directions_router
from app.routers.product_feedback import router as product_feedback_router
from app.routers.profile import router as profile_router
from app.routers.result import router as result_router
from app.routers.roadmap import router as roadmap_router
from app.routers.subject_readiness import router as subject_readiness_router
from app.routers.university import router as university_router
from app.routers.simulation import router as simulation_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/api/v1/auth")
api_router.include_router(admin_router, prefix="/api/v1/admin")
api_router.include_router(profile_router, prefix="/api/v1/profile")
api_router.include_router(artifacts_router, prefix="/api/v1/profile/artifacts")
api_router.include_router(assessment_router, prefix="/api/v1/assessment")
api_router.include_router(akinator_router, prefix="/api/v1/assessment")
api_router.include_router(simulation_router, prefix="/api/v1/assessment")
api_router.include_router(directions_router, prefix="/api/v1/directions")
api_router.include_router(product_feedback_router, prefix="/api/v1/feedback")
api_router.include_router(result_router, prefix="/api/v1/result")
api_router.include_router(roadmap_router, prefix="/api/v1/roadmap")
api_router.include_router(subject_readiness_router, prefix="/api/v1/subject-readiness")
api_router.include_router(university_router, prefix="/api/v1/universities")
