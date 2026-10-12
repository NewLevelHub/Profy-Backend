"""
Invite an admin by email and print the invitation link (PRO-466).
No password: the invitee sets it when accepting the link.
Run inside the api container:
  docker compose exec api python scripts/create_admin_user.py <email> [--locale ru|kk]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.user import UserRole  # noqa: E402
from scripts.staff_invitation_cli import run  # noqa: E402

if __name__ == "__main__":
    run(UserRole.admin)
