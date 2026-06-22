from app.database import Base
from app.models.user import User  # noqa: F401 — keep model imported so Alembic discovers it

__all__ = ["Base", "User"]
