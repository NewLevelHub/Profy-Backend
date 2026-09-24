from fastapi import APIRouter

from app.routers.admin import router as admin_router
from app.routers.artifacts import router as artifacts_router
from app.routers.assessment import router as assessment_router
from app.routers.astur import router as astur_router
from app.routers.auth import router as auth_router
from app.routers.belbin import router as belbin_router
from app.routers.certificates import router as certificates_router
from app.routers.extended_blocks import router as extended_blocks_router
from app.routers.motivation import router as motivation_router
from app.routers.motivation_pairs import router as motivation_pairs_router
from app.routers.profile import router as profile_router
from app.routers.psychoemotional import router as psychoemotional_router
from app.routers.psychologist import router as psychologist_router
from app.routers.question_pairs import router as question_pairs_router
from app.routers.questions import router as questions_router
from app.routers.result import router as result_router
from app.routers.university import router as university_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/api/v1/auth")
api_router.include_router(admin_router, prefix="/api/v1/admin")
api_router.include_router(psychologist_router, prefix="/api/v1/psychologist")
api_router.include_router(profile_router, prefix="/api/v1/profile")
api_router.include_router(artifacts_router, prefix="/api/v1/profile/artifacts")
api_router.include_router(certificates_router, prefix="/api/v1/profile/certificates")
api_router.include_router(assessment_router, prefix="/api/v1/assessment")
api_router.include_router(questions_router, prefix="/api/v1/assessment")
api_router.include_router(question_pairs_router, prefix="/api/v1/assessment")
api_router.include_router(motivation_router, prefix="/api/v1/assessment")
api_router.include_router(motivation_pairs_router, prefix="/api/v1/assessment")
api_router.include_router(psychoemotional_router, prefix="/api/v1/assessment")
api_router.include_router(belbin_router, prefix="/api/v1/assessment")
api_router.include_router(astur_router, prefix="/api/v1/assessment")
api_router.include_router(extended_blocks_router, prefix="/api/v1/assessment")
api_router.include_router(result_router, prefix="/api/v1/result")
api_router.include_router(university_router, prefix="/api/v1/universities")
