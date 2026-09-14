from app.database import Base
from app.models.analysis_result import AnalysisResult  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.email_verification import EmailVerificationToken  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.artifact import Artifact  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.assessment import Assessment  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.assessment_validity import AssessmentValidity  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.consent import Consent  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.direction import Direction  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.direction_inquiry import DirectionInquiry  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.direction_roadmap import DirectionRoadmap  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.motivation import MotivationResponse, MotivationStatement  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.motivation_pair import MotivationPair, MotivationPairResponse  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.password_reset import PasswordResetToken  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.product_feedback import ProductFeedback  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.profile import Profile  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.program import Program  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.psychoemotional_run import PsychoEmotionalRun  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.psychologist_note import PsychologistNote  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.question import Question  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.question_pair import QuestionPair  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.roadmap import Roadmap  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.university import University  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.university_image import UniversityImage  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.university_external_ref import UniversityExternalRef  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.user import User  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.user_response import UserResponse  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.validity_calibration_log import ValidityCalibrationLog  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.goal_overlay import GoalOverlay  # noqa: F401 — keep model imported so Alembic discovers it

__all__ = [
    "Base", "AnalysisResult", "AssessmentValidity", "Artifact", "Assessment", "Consent",
    "Direction", "DirectionInquiry", "DirectionRoadmap",
    "EmailVerificationToken", "MotivationPair", "MotivationPairResponse",
    "MotivationResponse", "MotivationStatement", "PasswordResetToken",
    "ProductFeedback", "Profile", "Program", "PsychoEmotionalRun",
    "PsychologistNote", "Question", "QuestionPair", "Roadmap",
    "University", "UniversityImage", "UniversityExternalRef",
    "User", "UserResponse", "ValidityCalibrationLog", "GoalOverlay",
]
