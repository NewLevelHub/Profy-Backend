"""reconcile users.role: PRO-291 seam -> real role system (pro-281)

Originally (pro-281) this migration *created* `user_role_enum` + `users.role`.
On `pro-282` the PRO-291 foundation migration `c9f21d7e4a3b` already created
both — as an inert seam with values `('user', 'staff', 'psychologist',
'admin')` and everyone defaulting to `'user'`. This revision now *reconciles*
that seam with the role system merged from pro-281:

- rename the enum value `user` -> `student` (same pg_enum OID, so existing
  rows and the column default relabel transparently);
- `staff` is left as a vestigial, unused label — Postgres can't drop an enum
  value in place; a later cleanup migration can recreate the type without it;
- give `users.is_admin` a server default — the model no longer maps it
  (`User.is_admin` is now a computed property over `role`), so INSERTs stop
  sending it and the existing NOT NULL would otherwise break.

Chained after the whole pro-282 psych-block migration run so history stays
linear (no merge node).

Revision ID: 12cdf8d6ab06
Revises: f3d9a1c2e6b8
Create Date: 2026-09-09 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "12cdf8d6ab06"
down_revision: str | None = "f3d9a1c2e6b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `c9f21d7e4a3b` already: CREATE TYPE user_role_enum (...'user'...),
    # ADD users.role NOT NULL DEFAULT 'user', backfilled admins.
    op.execute("ALTER TYPE user_role_enum RENAME VALUE 'user' TO 'student'")
    # Re-assert the admin backfill (idempotent — harmless if already done).
    op.execute("UPDATE users SET role = 'admin' WHERE is_admin IS TRUE")
    # Model stops sending `is_admin` on INSERT (now derived from `role`).
    op.alter_column("users", "is_admin", server_default=sa.false())


def downgrade() -> None:
    op.alter_column("users", "is_admin", server_default=None)
    op.execute("ALTER TYPE user_role_enum RENAME VALUE 'student' TO 'user'")
