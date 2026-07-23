from app.database import Base
from app.models.akinator_answer_log import AkinatorAnswerLog  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.akinator_question import AkinatorQuestion  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.email_verification import EmailVerificationToken  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.artifact import Artifact  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.assessment import Assessment  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.assessment_session import AssessmentSession  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.direction import Direction  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.direction_roadmap import DirectionRoadmap  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.password_reset import PasswordResetToken  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.profile import Profile  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.program import Program  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.university import University  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.user import User  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.product_feedback import ProductFeedback  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.profession_simulation import ProfessionSimulation  # noqa: F401
from app.models.profession_simulation_log import ProfessionSimulationLog  # noqa: F401
from app.models.subject_question import SubjectQuestion  # noqa: F401 — keep model imported so Alembic discovers it
from app.models.subject_readiness_session import SubjectReadinessSession  # noqa: F401 — keep model imported so Alembic discovers it

__all__ = [
    "Base", "AkinatorAnswerLog", "AkinatorQuestion", "Artifact", "Assessment", "AssessmentSession",
    "Direction", "DirectionRoadmap",
    "EmailVerificationToken", "PasswordResetToken", "Profile", "Program", "ProductFeedback", "University", "User",
    "ProfessionSimulation", "ProfessionSimulationLog",
    "SubjectQuestion", "SubjectReadinessSession",
]
