import enum
import uuid

from sqlalchemy import Enum, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class HollandType(str, enum.Enum):
    R = "R"
    I = "I"
    A = "A"
    S = "S"
    E = "E"
    C = "C"


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    riasec_type: Mapped[HollandType] = mapped_column(
        Enum(HollandType, name="holland_type_enum"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(String, nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
