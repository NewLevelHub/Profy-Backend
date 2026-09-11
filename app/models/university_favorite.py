import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UniversityFavorite(Base):
    """A university a student starred (PRO-265).

    User-level, not assessment-level: a favourite outlives any single
    assessment run and stays meaningful after a retake, so the FK goes
    straight to `users.id` (the ProductFeedback precedent) rather than
    through `profiles`/`assessments` the way Artifact/Certificate do. Both
    FKs are hard cascades — scripts/delete_user.py relies on the user side,
    and a starred row is meaningless once its university is gone.

    The (user_id, university_id) uniqueness is what makes starring
    idempotent: the service can rely on the DB to reject a double-star
    instead of racing a SELECT-then-INSERT check.
    """

    __tablename__ = "university_favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "university_id", name="uq_university_favorites_user_university"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    university_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("universities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
